"""Manifest CSV builder.

We don't bring up real SQL Server / S3. The Database is a MagicMock
whose read_sql_query returns a controlled DataFrame; the S3 client is
a MagicMock so we can assert on the PutObject call shape.
"""
from unittest.mock import MagicMock

import pandas as pd
import pytest

from manifest_builder import (
    build_manifest_dataframe,
    add_provenance_urls,
    write_manifest,
)


def _sample_rows(n: int = 2):
    return pd.DataFrame([
        {
            "part_number": f"AB{i:03d}",
            "description": f"brake disc {i}",
            "final_url": f"https://acme-bucket/tenants/acme/final/{i}.png",
            "source_url": f"https://example.com/img{i}.png",
            "candidate_count": 8,
            "discarded_by_dedup": 7,
            "hash_method": "phash",
            "hash_threshold": 14,
            "delivered_at": "2026-05-23T12:30:00",
        }
        for i in range(n)
    ])


def test_build_manifest_dataframe_calls_join_query():
    db = MagicMock()
    db.read_sql_query.return_value = _sample_rows()
    df = build_manifest_dataframe(db, "acme-parts")

    assert len(df) == 2
    assert list(df.columns)[:3] == ["part_number", "description", "final_url"]
    # Provenance join present.
    sql = db.read_sql_query.call_args.args[0]
    assert "LEFT JOIN" in sql
    assert "dbo.image_provenance" in sql
    assert "tenant_id = :tenant_id" in sql
    assert db.read_sql_query.call_args.kwargs["params"] == {"tenant_id": "acme-parts"}


def test_build_manifest_dataframe_falls_back_when_provenance_table_missing():
    db = MagicMock()
    # First call (provenance join) raises; second call (parts-only) returns rows.
    db.read_sql_query.side_effect = [
        RuntimeError("Invalid object name 'dbo.image_provenance'"),
        pd.DataFrame([{
            "part_number": "AB001",
            "description": "disc",
            "final_url": "https://acme/final/x.png",
        }]),
    ]
    df = build_manifest_dataframe(db, "acme-parts")
    assert len(df) == 1
    # Provenance columns are present but null.
    assert "source_url" in df.columns
    assert df["source_url"].iloc[0] is None
    assert df["candidate_count"].iloc[0] is None


def test_add_provenance_urls_with_base():
    df = pd.DataFrame([
        {"part_number": "AB123"},
        {"part_number": "AB456"},
    ])
    out = add_provenance_urls(df, "https://operator.example.com")
    assert out["provenance_url"].tolist() == [
        "https://operator.example.com/provenance?part_number=AB123",
        "https://operator.example.com/provenance?part_number=AB456",
    ]


def test_add_provenance_urls_strips_trailing_slash_on_base():
    df = pd.DataFrame([{"part_number": "AB123"}])
    out = add_provenance_urls(df, "https://operator.example.com/")
    assert out["provenance_url"].iloc[0] == "https://operator.example.com/provenance?part_number=AB123"


def test_add_provenance_urls_relative_when_no_base():
    df = pd.DataFrame([{"part_number": "AB123"}])
    out = add_provenance_urls(df, None)
    assert out["provenance_url"].iloc[0] == "/provenance?part_number=AB123"


def test_add_provenance_urls_empty_dataframe_keeps_column():
    df = pd.DataFrame({"part_number": []})
    out = add_provenance_urls(df, "https://x")
    assert "provenance_url" in out.columns
    assert len(out) == 0


def test_write_manifest_uploads_csv_with_attachment_header():
    db = MagicMock()
    db.read_sql_query.return_value = _sample_rows(3)
    s3 = MagicMock()
    s3.generate_presigned_url.return_value = "https://signed/manifest"

    refs = write_manifest(
        db,
        tenant_id="acme-parts",
        job_id="20260523T120000-deadbeef",
        bucket="acme-bucket",
        operator_base_url="https://op.example.com",
        s3=s3,
    )

    s3.put_object.assert_called_once()
    kw = s3.put_object.call_args.kwargs
    assert kw["Bucket"] == "acme-bucket"
    assert kw["Key"] == "tenants/acme-parts/reports/20260523T120000-deadbeef/manifest.csv"
    assert kw["ContentType"].startswith("text/csv")
    assert 'filename="manifest-20260523T120000-deadbeef.csv"' in kw["ContentDisposition"]

    # CSV body checks.
    body = kw["Body"].decode("utf-8")
    assert "part_number,description,final_url" in body.splitlines()[0]
    assert "provenance_url" in body.splitlines()[0]
    # 3 sample rows + header.
    assert len([line for line in body.splitlines() if line]) == 4
    # Provenance link wired correctly.
    assert "https://op.example.com/provenance?part_number=AB000" in body

    assert refs["key"].endswith("/manifest.csv")
    assert refs["url"] == "https://signed/manifest"
    assert refs["rows"] == 3


def test_write_manifest_validates_tenant_id():
    from tenancy.ids import InvalidTenantError
    db = MagicMock()
    db.read_sql_query.return_value = _sample_rows()
    with pytest.raises(InvalidTenantError):
        write_manifest(
            db,
            tenant_id="BAD TENANT",
            job_id="job-1",
            bucket="b",
            s3=MagicMock(),
        )


def test_write_manifest_with_zero_rows_still_uploads():
    """Empty manifest is a valid artefact — operator might run on a
    catalogue with no qualifying parts; we want the empty CSV to ship
    so the customer doesn't think the run silently dropped data."""
    db = MagicMock()
    db.read_sql_query.return_value = pd.DataFrame(columns=[
        "part_number", "description", "final_url",
        "source_url", "candidate_count", "discarded_by_dedup",
        "hash_method", "hash_threshold", "delivered_at",
    ])
    s3 = MagicMock()
    s3.generate_presigned_url.return_value = "https://signed/x"

    refs = write_manifest(
        db, tenant_id="acme",
        job_id="job-1", bucket="b", s3=s3,
    )
    assert refs["rows"] == 0
    body = s3.put_object.call_args.kwargs["Body"].decode("utf-8")
    # Just the header row.
    assert body.splitlines()[0].startswith("part_number")


def test_write_manifest_preferred_column_order():
    """The CSV should put customer-relevant columns first."""
    db = MagicMock()
    db.read_sql_query.return_value = _sample_rows(1)
    s3 = MagicMock()
    s3.generate_presigned_url.return_value = "https://signed/x"

    write_manifest(db, tenant_id="acme", job_id="j", bucket="b", s3=s3)
    body = s3.put_object.call_args.kwargs["Body"].decode("utf-8")
    header = body.splitlines()[0]
    # part_number, description, final_url come first.
    cols = header.split(",")
    assert cols[0] == "part_number"
    assert cols[1] == "description"
    assert cols[2] == "final_url"
    # source_url before the dedup machinery, provenance_url near the end.
    assert cols.index("source_url") < cols.index("hash_method")
    assert cols.index("provenance_url") > cols.index("hash_threshold")
