"""The operator Helper stamps tenant_id on every outbound SQS message.

These tests don't touch real AWS; they hand Helper a mock db (whose
``s3`` attribute is a MagicMock) and an SQS MagicMock, then verify:

- chunk uploads land under the tenant prefix
- ``send_chunk_messages`` emits a tenancy envelope with tenant_id +
  s3_key + job_id
- a helper with no active tenant refuses to submit work
- the BatchWatermarkDetector get_urls_from_db is called with tenant_id
"""
import json
from unittest.mock import MagicMock

import pandas as pd
import pytest

from helpers import Helper


@pytest.fixture
def helper(monkeypatch):
    monkeypatch.setenv("BUCKET", "acme-bucket")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    db = MagicMock()
    db.s3 = MagicMock()
    detector = MagicMock()
    h = Helper(db=db, detector=detector, tenant_id="acme-parts")
    # Replace boto clients with mocks (Helper constructs them in __init__).
    h.sqs = MagicMock()
    h.ec2 = MagicMock()
    return h


def test_split_data_uploads_under_tenant_prefix(helper):
    df = pd.DataFrame({"number": list("ABCDE"), "description": ["x"] * 5})
    helper.split_data_and_upload_jobs(
        df=df, bucket="acme-bucket", prefix="search_jobs", chunk_size=2,
    )

    keys = [
        c.kwargs["Key"]
        for c in helper.db.s3.put_object.call_args_list
    ]
    assert keys == [
        "tenants/acme-parts/search_jobs/chunk_1.csv",
        "tenants/acme-parts/search_jobs/chunk_2.csv",
        "tenants/acme-parts/search_jobs/chunk_3.csv",
    ]


def test_send_chunk_messages_uses_envelope(helper):
    helper.send_chunk_messages(
        job_id="20260101T000000-aaaa",
        queue_url="https://sqs/queue",
        num_chunks=3,
        key="search_jobs",
    )

    assert helper.sqs.send_message.call_count == 3
    for i, call in enumerate(helper.sqs.send_message.call_args_list, start=1):
        body = json.loads(call.kwargs["MessageBody"])
        assert body["v"] == 1
        assert body["tenant_id"] == "acme-parts"
        assert body["s3_key"] == f"tenants/acme-parts/search_jobs/chunk_{i}.csv"
        assert body["job_id"] == "20260101T000000-aaaa"
        assert "submitted_at" in body


def test_helper_without_tenant_refuses_work():
    h = Helper(db=MagicMock(), detector=MagicMock())  # no tenant
    h.sqs = MagicMock()
    with pytest.raises(RuntimeError, match="no active tenant_id"):
        h.send_chunk_messages("job", "url", 1, "search_jobs")


def test_set_tenant_validates(helper):
    from tenancy.ids import InvalidTenantError
    with pytest.raises(InvalidTenantError):
        helper.set_tenant("BAD TENANT")
    assert helper.tenant_id == "acme-parts"  # unchanged


def test_organize_and_submit_batch_passes_tenant_through(helper, monkeypatch):
    helper.detector.get_urls_from_db.return_value = pd.Series([])
    ids, batch_map = helper.organize_and_submit_batch()
    helper.detector.get_urls_from_db.assert_called_once_with(tenant_id="acme-parts")
    assert ids == []
    assert batch_map == {}


def test_organize_and_submit_batch_uses_tenant_scoped_base(helper):
    helper.detector.get_urls_from_db.return_value = pd.Series([
        f"https://acme-bucket.s3.us-east-1.amazonaws.com/tenants/acme-parts/images/AB123_disc_0.png"
    ])
    helper.detector.create_batch_requests.return_value = [{"custom_id": "x"}]
    helper.detector.submit_batch.return_value = "batch_abc"

    ids, batch_map = helper.organize_and_submit_batch()

    helper.detector.submit_batch.assert_called_once()
    kwargs = helper.detector.submit_batch.call_args.kwargs
    assert kwargs["tenant_id"] == "acme-parts"
    assert ids == ["batch_abc"]
    # batch_map ties the OpenAI batch id back to the on-disk jsonl
    # so the resubmit-failed flow can re-upload it later.
    assert batch_map == {"batch_abc": "data/ai_sent_data/batch_0.jsonl"}


def test_resubmit_failed_batches_reuploads_each_jsonl(helper):
    helper.detector.resubmit_batch_from_disk.side_effect = ["new_1", "new_2"]
    failed_map = {
        "old_1": "data/ai_sent_data/batch_0.jsonl",
        "old_2": "data/ai_sent_data/batch_1.jsonl",
    }
    new_ids, new_map = helper.resubmit_failed_batches(failed_map)
    assert sorted(new_ids) == ["new_1", "new_2"]
    assert "data/ai_sent_data/batch_0.jsonl" in new_map.values()
    assert "data/ai_sent_data/batch_1.jsonl" in new_map.values()
    assert helper.detector.resubmit_batch_from_disk.call_count == 2


def test_resubmit_failed_batches_skips_missing_input_files(helper):
    helper.detector.resubmit_batch_from_disk.side_effect = [
        FileNotFoundError("gone"),
        "new_2",
    ]
    failed_map = {
        "old_1": "data/ai_sent_data/batch_0.jsonl",
        "old_2": "data/ai_sent_data/batch_1.jsonl",
    }
    new_ids, new_map = helper.resubmit_failed_batches(failed_map)
    assert new_ids == ["new_2"]
    assert "new_2" in new_map


def test_resubmit_failed_batches_requires_tenant(helper):
    helper.tenant_id = None
    with pytest.raises(RuntimeError, match="no active tenant_id"):
        helper.resubmit_failed_batches({"x": "y.jsonl"})
