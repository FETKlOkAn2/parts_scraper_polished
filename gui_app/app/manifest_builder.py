"""Build a customer-shareable CSV manifest of every delivered image.

This is the artefact an e-shop owner actually wants out of a run: a
spreadsheet with one row per delivered SKU, ready to paste into
their PIM/ERP. The HTML report sells the run; the manifest CSV is
what gets used.

One row per part that has a non-null ``final_tag``. Columns:

    part_number          dbo.parts.number
    description          dbo.parts.description
    final_url            dbo.parts.final_tag         (the customer-facing image URL)
    source_url           dbo.image_provenance.source_url (where the candidate came from)
    candidate_count      dbo.image_provenance.candidate_count
    discarded_by_dedup   dbo.image_provenance.discarded_by_dedup
    hash_method          dbo.image_provenance.hash_method
    hash_threshold       dbo.image_provenance.hash_threshold
    provenance_url       deep link into /provenance?part_number=...
    delivered_at         dbo.image_provenance.created_at

We do this as a LEFT JOIN so parts without provenance still show up —
single-tenant deployments that haven't applied migration 005 keep
working, just with the provenance columns empty.

Builds in pandas, writes to ``s3://<bucket>/tenants/<id>/reports/<job_id>/manifest.csv``.
Returns the S3 key + a presigned URL valid for 7 days.
"""
from __future__ import annotations

import io
import os
from typing import Optional

import boto3
import pandas as pd

from obs import get_logger
from tenancy import TenantPaths

_log = get_logger("operator.manifest")


_MANIFEST_SQL = """
SELECT
    p.[number]                              AS part_number,
    p.description                           AS description,
    p.final_tag                             AS final_url,
    pr.source_url                           AS source_url,
    pr.candidate_count                      AS candidate_count,
    pr.discarded_by_dedup                   AS discarded_by_dedup,
    pr.hash_method                          AS hash_method,
    pr.hash_threshold                       AS hash_threshold,
    pr.created_at                           AS delivered_at
FROM dbo.parts AS p
LEFT JOIN (
    -- For each part, keep only the most recent provenance row. A
    -- catalogue that's been processed multiple times has multiple
    -- provenance rows; the manifest shows what was delivered now.
    SELECT prov.*,
           ROW_NUMBER() OVER (
               PARTITION BY prov.tenant_id, prov.part_number
               ORDER BY prov.created_at DESC
           ) AS rn
    FROM dbo.image_provenance AS prov
    WHERE prov.tenant_id = :tenant_id
) AS pr
    ON pr.tenant_id = p.tenant_id
   AND pr.part_number = p.[number]
   AND pr.rn = 1
WHERE p.tenant_id = :tenant_id
  AND p.final_tag IS NOT NULL
ORDER BY p.[number] ASC;
"""


def build_manifest_dataframe(db, tenant_id: str) -> pd.DataFrame:
    """Return the manifest as a DataFrame.

    Side-effect-free; callers serialise the result however they want
    (CSV for the customer, JSON for an API, etc.). Provenance columns
    are NaN/None for parts without a provenance row, which happens on
    single-tenant deployments that haven't run migration 005.
    """
    try:
        df = db.read_sql_query(_MANIFEST_SQL, params={"tenant_id": tenant_id})
    except Exception as e:
        # Provenance table might not exist; fall back to a parts-only
        # query so the manifest still ships.
        _log.warning(
            "manifest provenance join failed; falling back to parts-only",
            error=str(e),
        )
        df = db.read_sql_query(
            """
            SELECT [number] AS part_number,
                   description,
                   final_tag AS final_url
            FROM dbo.parts
            WHERE tenant_id = :tenant_id AND final_tag IS NOT NULL
            ORDER BY [number] ASC;
            """,
            params={"tenant_id": tenant_id},
        )
        for col in ("source_url", "candidate_count", "discarded_by_dedup",
                    "hash_method", "hash_threshold", "delivered_at"):
            df[col] = None
    return df


def add_provenance_urls(df: pd.DataFrame, base_url: Optional[str]) -> pd.DataFrame:
    """Attach a ``provenance_url`` column.

    ``base_url`` is the operator console's external URL (e.g.
    ``https://operator.example.com``). If unset (typical for single-
    tenant deployments running the Tkinter GUI without the web
    console), we emit a relative path that's still useful when the
    operator imports the CSV into a tool that can resolve it.
    """
    base = (base_url or "").rstrip("/")
    if df.empty:
        df = df.copy()
        df["provenance_url"] = []
        return df

    def _link(part):
        if not part:
            return ""
        path = f"/provenance?part_number={part}"
        return f"{base}{path}" if base else path

    df = df.copy()
    df["provenance_url"] = df["part_number"].apply(_link)
    return df


def write_manifest(
    db,
    *,
    tenant_id: str,
    job_id: str,
    bucket: str,
    region: Optional[str] = None,
    operator_base_url: Optional[str] = None,
    s3=None,
) -> dict:
    """Build + upload the manifest CSV.

    Returns ``{key, url}`` where ``url`` is a 7-day pre-signed link
    suitable for emailing the customer.
    """
    region = region or os.getenv("AWS_REGION", "us-east-1")
    s3 = s3 or boto3.client("s3", region_name=region)

    df = build_manifest_dataframe(db, tenant_id)
    df = add_provenance_urls(df, operator_base_url or os.getenv("OPERATOR_BASE_URL"))

    # Reorder columns for the customer-facing CSV. Drop nothing — even
    # nulls are useful in a spreadsheet.
    preferred = [
        "part_number", "description", "final_url",
        "source_url", "candidate_count", "discarded_by_dedup",
        "hash_method", "hash_threshold", "provenance_url", "delivered_at",
    ]
    cols = [c for c in preferred if c in df.columns] + [
        c for c in df.columns if c not in preferred
    ]
    df = df[cols]

    buf = io.StringIO()
    df.to_csv(buf, index=False)
    body = buf.getvalue().encode("utf-8")

    paths = TenantPaths(tenant_id)
    key = f"{paths.report_prefix(job_id)}/manifest.csv"
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="text/csv; charset=utf-8",
        # Browser-friendly download with a sensible filename.
        ContentDisposition=f'attachment; filename="manifest-{job_id}.csv"',
    )

    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=7 * 24 * 3600,
    )

    _log.info(
        "manifest written",
        tenant_id=tenant_id,
        job_id=job_id,
        bucket=bucket,
        key=key,
        rows=int(len(df)),
    )
    return {"key": key, "url": url, "rows": int(len(df))}
