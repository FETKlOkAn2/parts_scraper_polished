"""End-to-end-ish tests for the resubmit-only-failed-batches workflow."""
import json
import os
from unittest.mock import MagicMock

import pandas as pd
import pytest

from helpers import Helper
from batch_watermark_detector import BatchUnusableError


@pytest.fixture
def helper(monkeypatch):
    monkeypatch.setenv("BUCKET", "acme-bucket")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    db = MagicMock()
    db.s3 = MagicMock()
    detector = MagicMock()
    h = Helper(db=db, detector=detector, tenant_id="acme-parts")
    h.sqs = MagicMock()
    h.ec2 = MagicMock()
    return h


def _fake_batch(status, output_file_id="out_x", error_file_id=None):
    b = MagicMock()
    b.status = status
    b.output_file_id = output_file_id
    b.error_file_id = error_file_id
    return b


def test_parse_ai_results_attaches_resubmit_map_to_exception(helper, tmp_path, monkeypatch):
    """When OpenAI batches end in failed/expired, the BatchUnusableError
    carries a {failed_batch_id: jsonl_path} map so the GUI's resubmit
    button knows what to re-upload."""
    monkeypatch.chdir(tmp_path)  # so data/ai_output/ writes are scoped

    # Two batches: one usable, one failed.
    helper.detector.client.batches.retrieve.side_effect = [
        _fake_batch("completed", output_file_id="out_1"),
        _fake_batch("failed", output_file_id=None),
    ]
    helper.detector.download_results = MagicMock()
    helper.detector.parse_results = MagicMock(return_value={})

    batch_map = {
        "batch_completed": "data/ai_sent_data/batch_0.jsonl",
        "batch_failed":    "data/ai_sent_data/batch_1.jsonl",
    }

    with pytest.raises(BatchUnusableError) as excinfo:
        helper.parse_ai_results(
            ["batch_completed", "batch_failed"],
            batch_map=batch_map,
        )

    err = excinfo.value
    assert err.resubmit_map == {
        "batch_failed": "data/ai_sent_data/batch_1.jsonl"
    }
    assert err.unusable == [("batch_failed", "failed")]


def test_parse_ai_results_with_no_batch_map_still_records_unusable(helper, tmp_path, monkeypatch):
    """If the caller doesn't pass batch_map, we still raise the error,
    we just can't help with resubmit (the map values are all None)."""
    monkeypatch.chdir(tmp_path)
    helper.detector.client.batches.retrieve.return_value = _fake_batch(
        "expired", output_file_id=None
    )

    with pytest.raises(BatchUnusableError) as excinfo:
        helper.parse_ai_results(["batch_expired"])

    assert excinfo.value.resubmit_map == {"batch_expired": None}


def test_resubmit_batch_from_disk_raises_on_missing_file(tmp_path):
    """The detector's resubmit_batch_from_disk refuses to invent input."""
    from batch_watermark_detector import BatchWatermarkDetector

    det = BatchWatermarkDetector.__new__(BatchWatermarkDetector)
    det.client = MagicMock()
    with pytest.raises(FileNotFoundError):
        det.resubmit_batch_from_disk(
            jsonl_path=str(tmp_path / "does-not-exist.jsonl"),
            tenant_id="acme",
        )


def test_resubmit_batch_from_disk_uploads_existing_file(tmp_path):
    from batch_watermark_detector import BatchWatermarkDetector

    p = tmp_path / "batch_0.jsonl"
    p.write_text(json.dumps({"custom_id": "x"}) + "\n")

    det = BatchWatermarkDetector.__new__(BatchWatermarkDetector)
    det.client = MagicMock()
    det.client.files.create.return_value = MagicMock(id="file_abc")
    det.client.batches.create.return_value = MagicMock(id="batch_new")

    out = det.resubmit_batch_from_disk(jsonl_path=str(p), tenant_id="acme")

    assert out == "batch_new"
    det.client.files.create.assert_called_once()
    det.client.batches.create.assert_called_once()
    create_kwargs = det.client.batches.create.call_args.kwargs
    assert create_kwargs["input_file_id"] == "file_abc"
    # Tenant id flows into the metadata for post-hoc attribution.
    assert create_kwargs["metadata"]["tenant_id"] == "acme"
