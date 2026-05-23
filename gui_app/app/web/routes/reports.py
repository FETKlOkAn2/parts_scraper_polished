"""Reports list + provenance lookup.

  GET /reports             — list runs that produced a report URL.
  GET /provenance          — search box; on submit, lists every
                             provenance row for the given part_number
                             or job_id (tenant-scoped via SESSION_CONTEXT).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request

from database import Database
from tenancy import RunsRepository

from ..deps import active_tenant, db as db_dep

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


@router.get("/reports", response_class=None)
def reports_index(request: Request, db: Database = Depends(db_dep)):
    tid = active_tenant(request)
    try:
        runs = RunsRepository(db).list_recent(tenant_id=tid, limit=100)
        # Only show runs that have a published report URL.
        with_reports = [r for r in runs if r.report_html_url]
        error = None
    except Exception as e:
        with_reports = []
        error = str(e)
    return _templates(request).TemplateResponse(
        request,
        "reports_index.html",
        {
            "active_tenant": tid,
            "runs": with_reports,
            "error": error,
        },
    )


@router.get("/provenance", response_class=None)
def provenance_index(
    request: Request,
    part_number: Optional[str] = None,
    job_id: Optional[str] = None,
    db: Database = Depends(db_dep),
):
    rows = []
    error = None
    if part_number or job_id:
        try:
            if part_number:
                df = db.read_sql_query(
                    """
                    SELECT TOP 200 part_number, job_id, source_url,
                           candidate_count, discarded_by_dedup,
                           hash_method, hash_size, hash_threshold,
                           final_key, final_url, created_at
                    FROM dbo.image_provenance
                    WHERE part_number = :p
                    ORDER BY created_at DESC;
                    """,
                    params={"p": part_number},
                )
            else:
                df = db.read_sql_query(
                    """
                    SELECT TOP 200 part_number, job_id, source_url,
                           candidate_count, discarded_by_dedup,
                           hash_method, hash_size, hash_threshold,
                           final_key, final_url, created_at
                    FROM dbo.image_provenance
                    WHERE job_id = :j
                    ORDER BY part_number ASC;
                    """,
                    params={"j": job_id},
                )
            rows = df.to_dict(orient="records")
        except Exception as e:
            error = str(e)

    return _templates(request).TemplateResponse(
        request,
        "provenance.html",
        {
            "active_tenant": active_tenant(request),
            "rows": rows,
            "error": error,
            "part_number": part_number or "",
            "job_id": job_id or "",
        },
    )
