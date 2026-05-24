"""Production-hardening regression tests.

These guard the lessons from the first US deployment's debrief:
- OpenAI Batch enforces a per-batch size cap; the operator console
  default must respect it.
- Image-search backend is pluggable (Bing vs DuckDuckGo).
- Shard distribution defaults to interleaved so a scraping outage's
  blast radius is bounded and pinpointable.
- Watermark classifier supports N-shot ensemble with majority vote.
- Base64 embedded images is a runtime opt-in that preserves the
  URL-passing default.
"""
import base64
import json
import os
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ---- A1: batch size + max_images defaults ------------------------------

def test_helper_batch_size_defaults_to_safe_ceiling(monkeypatch):
    """A bug in the first US deployment was the 40k default for
    max_batch_size, which silently broke at OpenAI's real ceiling."""
    monkeypatch.delenv("OPENAI_BATCH_MAX_ITEMS", raising=False)
    monkeypatch.setenv("BUCKET", "b")
    monkeypatch.setenv("AWS_REGION", "us-east-1")

    from helpers import Helper
    h = Helper(db=MagicMock(), detector=MagicMock(), tenant_id="acme")
    assert h.max_batch_size == 2000


def test_helper_batch_size_env_override(monkeypatch):
    monkeypatch.setenv("OPENAI_BATCH_MAX_ITEMS", "1500")
    monkeypatch.setenv("BUCKET", "b")
    from helpers import Helper
    h = Helper(db=MagicMock(), detector=MagicMock(), tenant_id="acme")
    assert h.max_batch_size == 1500


def test_parser_max_images_defaults_to_5(monkeypatch):
    monkeypatch.delenv("MAX_IMAGES_PER_PART", raising=False)
    monkeypatch.setenv("DECODO_USERNAME", "u")
    monkeypatch.setenv("DECODO_PASSWORD", "p")
    monkeypatch.setenv("BUCKET", "b")
    from scraper.parser import Parser
    p = Parser(db=MagicMock(), text="AB123 disc", tenant_id="acme")
    assert p.max_images == 5


def test_parser_max_images_env_override(monkeypatch):
    monkeypatch.setenv("MAX_IMAGES_PER_PART", "8")
    monkeypatch.setenv("DECODO_USERNAME", "u")
    monkeypatch.setenv("DECODO_PASSWORD", "p")
    monkeypatch.setenv("BUCKET", "b")
    from scraper.parser import Parser
    p = Parser(db=MagicMock(), text="x", tenant_id="acme")
    assert p.max_images == 8


# ---- A2: interleaved sharding ------------------------------------------

def _build_helper(monkeypatch):
    monkeypatch.setenv("BUCKET", "b")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    from helpers import Helper
    h = Helper(db=MagicMock(), detector=MagicMock(), tenant_id="acme")
    h.db.s3 = MagicMock()
    return h


def test_interleaved_shards_distribute_rows_round_robin(monkeypatch):
    h = _build_helper(monkeypatch)
    indices_by_chunk = {k: rows for k, rows in h._shard_indices(10, 3, "interleaved")}
    # 10 rows over 3 chunks, interleaved: chunk 0 takes 0,3,6,9;
    # chunk 1 takes 1,4,7; chunk 2 takes 2,5,8.
    assert indices_by_chunk[0] == [0, 3, 6, 9]
    assert indices_by_chunk[1] == [1, 4, 7]
    assert indices_by_chunk[2] == [2, 5, 8]
    # No row appears twice, all 10 rows are covered.
    flat = [i for rows in indices_by_chunk.values() for i in rows]
    assert sorted(flat) == list(range(10))


def test_block_shards_distribute_rows_contiguous(monkeypatch):
    h = _build_helper(monkeypatch)
    indices_by_chunk = {k: rows for k, rows in h._shard_indices(10, 3, "block")}
    assert indices_by_chunk[0] == [0, 1, 2, 3]
    assert indices_by_chunk[1] == [4, 5, 6, 7]
    assert indices_by_chunk[2] == [8, 9]


def test_default_shard_strategy_is_interleaved(monkeypatch, capsys):
    monkeypatch.delenv("SHARD_STRATEGY", raising=False)
    h = _build_helper(monkeypatch)
    df = pd.DataFrame({"number": [f"P{i}" for i in range(6)], "description": ["x"] * 6})
    h.split_data_and_upload_jobs(df, bucket="b", prefix="search_jobs", chunk_size=2)

    # Three chunks of two rows each; interleaved gives chunks the rows
    # 0,3 then 1,4 then 2,5.
    expected_chunk_contents = [
        ["P0", "P3"],
        ["P1", "P4"],
        ["P2", "P5"],
    ]
    assert h.db.s3.put_object.call_count == 3
    for call, expected in zip(h.db.s3.put_object.call_args_list, expected_chunk_contents):
        body = call.kwargs["Body"].decode("utf-8")
        rows = [line.split(",")[0] for line in body.strip().split("\n")]
        assert rows == expected, f"chunk had {rows}, expected {expected}"


def test_block_strategy_still_works(monkeypatch):
    monkeypatch.setenv("SHARD_STRATEGY", "block")
    h = _build_helper(monkeypatch)
    df = pd.DataFrame({"number": [f"P{i}" for i in range(6)], "description": ["x"] * 6})
    h.split_data_and_upload_jobs(df, bucket="b", prefix="search_jobs", chunk_size=2)

    # First chunk is the first contiguous 2 rows (P0, P1).
    first_body = h.db.s3.put_object.call_args_list[0].kwargs["Body"].decode("utf-8")
    rows = [line.split(",")[0] for line in first_body.strip().split("\n")]
    assert rows == ["P0", "P1"]


def test_unknown_strategy_falls_back_to_interleaved(monkeypatch):
    monkeypatch.setenv("SHARD_STRATEGY", "made-up")
    h = _build_helper(monkeypatch)
    df = pd.DataFrame({"number": [f"P{i}" for i in range(4)], "description": ["x"] * 4})
    h.split_data_and_upload_jobs(df, bucket="b", prefix="search_jobs", chunk_size=2)
    # First chunk under interleaved is rows 0 and 2.
    first_body = h.db.s3.put_object.call_args_list[0].kwargs["Body"].decode("utf-8")
    rows = [line.split(",")[0] for line in first_body.strip().split("\n")]
    assert rows == ["P0", "P2"]


# ---- A3: DuckDuckGo backend --------------------------------------------

def test_default_backend_is_bing(monkeypatch):
    monkeypatch.delenv("SEARCH_BACKEND", raising=False)
    monkeypatch.setenv("DECODO_USERNAME", "u")
    monkeypatch.setenv("DECODO_PASSWORD", "p")
    monkeypatch.setenv("BUCKET", "b")
    from scraper.parser import Parser
    p = Parser(db=MagicMock(), text="brake disc", tenant_id="acme")
    assert p.backend == "bing"
    assert "bing.com" in p.url


def test_duckduckgo_backend_url(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKEND", "duckduckgo")
    monkeypatch.setenv("DECODO_USERNAME", "u")
    monkeypatch.setenv("DECODO_PASSWORD", "p")
    monkeypatch.setenv("BUCKET", "b")
    from scraper.parser import Parser
    p = Parser(db=MagicMock(), text="brake disc", tenant_id="acme")
    assert p.backend == "duckduckgo"
    assert "duckduckgo.com" in p.url


def test_unknown_backend_falls_back_to_bing(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKEND", "altavista-1998")
    monkeypatch.setenv("DECODO_USERNAME", "u")
    monkeypatch.setenv("DECODO_PASSWORD", "p")
    monkeypatch.setenv("BUCKET", "b")
    from scraper.parser import Parser
    p = Parser(db=MagicMock(), text="x", tenant_id="acme")
    assert p.backend == "bing"


def test_duckduckgo_extracts_image_urls(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKEND", "duckduckgo")
    monkeypatch.setenv("DECODO_USERNAME", "u")
    monkeypatch.setenv("DECODO_PASSWORD", "p")
    monkeypatch.setenv("BUCKET", "b")
    from scraper.parser import Parser
    p = Parser(db=MagicMock(), text="brake disc", tenant_id="acme")

    # Provide a fake bootstrap response containing a vqd token, plus a
    # fake JSON results endpoint.
    p.session = MagicMock()
    json_response = MagicMock()
    json_response.json.return_value = {
        "results": [
            {"image": "https://example.com/a.png"},
            {"image": "https://example.com/b.png"},
            # Dup of the first — should be deduplicated.
            {"image": "https://example.com/a.png"},
        ]
    }
    json_response.raise_for_status = MagicMock()
    p.session.get.return_value = json_response

    urls = p._extract_links_duckduckgo("...vqd='123-4567'...")
    assert urls == ["https://example.com/a.png", "https://example.com/b.png"]


def test_duckduckgo_handles_missing_vqd(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKEND", "duckduckgo")
    monkeypatch.setenv("DECODO_USERNAME", "u")
    monkeypatch.setenv("DECODO_PASSWORD", "p")
    monkeypatch.setenv("BUCKET", "b")
    from scraper.parser import Parser
    p = Parser(db=MagicMock(), text="x", tenant_id="acme")
    p.session = MagicMock()
    urls = p._extract_links_duckduckgo("no token here")
    assert urls == []


# ---- B1: watermark ensemble --------------------------------------------

def test_create_batch_requests_n1_keeps_old_custom_id(monkeypatch):
    monkeypatch.delenv("WATERMARK_ENSEMBLE_SIZE", raising=False)
    from batch_watermark_detector import BatchWatermarkDetector
    d = BatchWatermarkDetector.__new__(BatchWatermarkDetector)
    d.client = MagicMock()
    requests_ = d.create_batch_requests(["https://x/AB123_disc_0.png"])
    assert len(requests_) == 1
    # Single-shot custom_id is just the basename.
    assert requests_[0]["custom_id"] == "AB123_disc_0.png"


def test_create_batch_requests_n5_emits_variants(monkeypatch):
    monkeypatch.setenv("WATERMARK_ENSEMBLE_SIZE", "5")
    from batch_watermark_detector import BatchWatermarkDetector
    d = BatchWatermarkDetector.__new__(BatchWatermarkDetector)
    d.client = MagicMock()
    requests_ = d.create_batch_requests(["https://x/AB123_disc_0.png"])
    assert len(requests_) == 5
    ids = {r["custom_id"] for r in requests_}
    assert ids == {f"AB123_disc_0.png#v{i}" for i in range(5)}
    # Variants use different temperatures so the model returns
    # uncorrelated samples.
    temps = {r["body"]["temperature"] for r in requests_}
    assert len(temps) >= 2


def test_ensemble_size_clamped_to_ten(monkeypatch):
    monkeypatch.setenv("WATERMARK_ENSEMBLE_SIZE", "9999")
    from batch_watermark_detector import BatchWatermarkDetector
    d = BatchWatermarkDetector.__new__(BatchWatermarkDetector)
    d.client = MagicMock()
    requests_ = d.create_batch_requests(["https://x/y.png"])
    assert len(requests_) == 10


def _write_jsonl(path, rows):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _vote_row(custom_id, has_watermark, confidence="high", wm_type="logo", description="x"):
    body = json.dumps({
        "has_watermark": has_watermark,
        "confidence": confidence,
        "watermark_type": wm_type,
        "description": description,
    })
    return {
        "custom_id": custom_id,
        "response": {
            "status_code": 200,
            "body": {
                "choices": [{"message": {"content": body}}],
            },
        },
    }


def test_parse_results_majority_vote_majority_flagged(tmp_path):
    from batch_watermark_detector import BatchWatermarkDetector
    d = BatchWatermarkDetector.__new__(BatchWatermarkDetector)
    d.db = MagicMock()
    d.db.delete_keys = []

    p = tmp_path / "batch.jsonl"
    # 3 of 5 votes say watermark → flagged.
    _write_jsonl(p, [
        _vote_row("img.png#v0", True),
        _vote_row("img.png#v1", True),
        _vote_row("img.png#v2", False),
        _vote_row("img.png#v3", True),
        _vote_row("img.png#v4", False),
    ])
    results = d.parse_results(str(p), tenant_id="acme")
    assert results["img.png"]["has_watermark"] is True
    assert results["img.png"]["votes_flagged"] == 3
    assert results["img.png"]["votes_total"] == 5
    assert len(d.db.delete_keys) == 1


def test_parse_results_majority_vote_minority_flagged(tmp_path):
    from batch_watermark_detector import BatchWatermarkDetector
    d = BatchWatermarkDetector.__new__(BatchWatermarkDetector)
    d.db = MagicMock()
    d.db.delete_keys = []

    p = tmp_path / "batch.jsonl"
    # 1 of 5 votes flagged → keep.
    _write_jsonl(p, [
        _vote_row("img.png#v0", True),
        _vote_row("img.png#v1", False),
        _vote_row("img.png#v2", False),
        _vote_row("img.png#v3", False),
        _vote_row("img.png#v4", False),
    ])
    results = d.parse_results(str(p), tenant_id="acme")
    assert results["img.png"]["has_watermark"] is False
    assert d.db.delete_keys == []


def test_parse_results_tie_flags(tmp_path):
    """On a tie (2/4) we default to flagged — matches the prompt's
    'when uncertain, prefer to flag' bias."""
    from batch_watermark_detector import BatchWatermarkDetector
    d = BatchWatermarkDetector.__new__(BatchWatermarkDetector)
    d.db = MagicMock()
    d.db.delete_keys = []

    p = tmp_path / "batch.jsonl"
    _write_jsonl(p, [
        _vote_row("img.png#v0", True),
        _vote_row("img.png#v1", True),
        _vote_row("img.png#v2", False),
        _vote_row("img.png#v3", False),
    ])
    results = d.parse_results(str(p), tenant_id="acme")
    assert results["img.png"]["has_watermark"] is True


def test_parse_results_n1_works_with_legacy_custom_id(tmp_path):
    """Single-shot mode: custom_id has no #v separator. The grouping
    code must still work."""
    from batch_watermark_detector import BatchWatermarkDetector
    d = BatchWatermarkDetector.__new__(BatchWatermarkDetector)
    d.db = MagicMock()
    d.db.delete_keys = []

    p = tmp_path / "batch.jsonl"
    _write_jsonl(p, [_vote_row("img.png", True)])
    results = d.parse_results(str(p), tenant_id="acme")
    assert results["img.png"]["has_watermark"] is True
    assert results["img.png"]["votes_total"] == 1


# ---- B2: base64 embedded images ----------------------------------------

def test_image_content_default_is_url(monkeypatch):
    monkeypatch.delenv("OPENAI_EMBED_IMAGES", raising=False)
    from batch_watermark_detector import BatchWatermarkDetector
    d = BatchWatermarkDetector.__new__(BatchWatermarkDetector)
    block = d._image_content("https://example.com/x.png")
    assert block == {"type": "image_url", "image_url": {"url": "https://example.com/x.png"}}


def test_image_content_embedded_downloads_and_base64_encodes(monkeypatch):
    monkeypatch.setenv("OPENAI_EMBED_IMAGES", "true")
    from batch_watermark_detector import BatchWatermarkDetector
    d = BatchWatermarkDetector.__new__(BatchWatermarkDetector)

    fake_resp = MagicMock()
    fake_resp.content = b"\x89PNG\r\n\x1a\nfakecontent"
    fake_resp.headers = {"Content-Type": "image/png"}
    fake_resp.raise_for_status = MagicMock()

    with patch("batch_watermark_detector.requests.get", return_value=fake_resp):
        block = d._image_content("https://example.com/x.png")

    url = block["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    decoded = base64.b64decode(url.split(",", 1)[1])
    assert decoded == b"\x89PNG\r\n\x1a\nfakecontent"


def test_image_content_embedded_falls_back_to_url_on_fetch_failure(monkeypatch):
    monkeypatch.setenv("OPENAI_EMBED_IMAGES", "true")
    from batch_watermark_detector import BatchWatermarkDetector
    d = BatchWatermarkDetector.__new__(BatchWatermarkDetector)

    with patch("batch_watermark_detector.requests.get", side_effect=RuntimeError("no network")):
        block = d._image_content("https://example.com/x.png")

    # Falls back to URL form so the batch still ships.
    assert block == {"type": "image_url", "image_url": {"url": "https://example.com/x.png"}}
