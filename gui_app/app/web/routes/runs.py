"""Run status pages.

  GET /runs                       — list recent runs (paginated).
  GET /runs/{job_id}              — full status page for one run.
  GET /runs/{job_id}/status       — HTMX partial fragment; the status
                                    page polls this every 5 seconds.

The status partial is what makes the page live. We return a small
HTML fragment (the stage pill + the progress_note + the buttons for
the next stage), and the parent page swaps it in place via HTMX.
That way a terminal browser tab doesn't fall behind reality and the
operator doesn't have to manually refresh.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from database import Database
from tenancy import RunsRepository

from ..deps import active_tenant, db as db_dep

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


@router.get("/runs", response_class=None)
def runs_index(request: Request, db: Database = Depends(db_dep)):
    tid = active_tenant(request)
    repo = RunsRepository(db)
    try:
        rows = repo.list_recent(tenant_id=tid, limit=50)
        error = None
    except Exception as e:
        rows = []
        error = str(e)
    return _templates(request).TemplateResponse(
        request,
        "runs_index.html",
        {
            "active_tenant": tid,
            "runs": rows,
            "error": error,
        },
    )


@router.get("/runs/{job_id}", response_class=None)
def run_detail(request: Request, job_id: str, db: Database = Depends(db_dep)):
    repo = RunsRepository(db)
    rec = repo.get(job_id)
    if rec is None:
        raise HTTPException(404, detail=f"run {job_id!r} not found")
    return _templates(request).TemplateResponse(
        request,
        "run_detail.html",
        {
            "active_tenant": active_tenant(request),
            "run": rec,
        },
    )


@router.get("/runs/{job_id}/status", response_class=None)
def run_status_partial(request: Request, job_id: str, db: Database = Depends(db_dep)):
    """HTMX partial: returns just the status block. Polled every 5s."""
    repo = RunsRepository(db)
    rec = repo.get(job_id)
    if rec is None:
        raise HTTPException(404, detail=f"run {job_id!r} not found")

    # Tell HTMX to stop polling once we hit a terminal state.
    headers = {}
    if rec.is_terminal:
        headers["HX-Trigger"] = "run-terminal"

    return _templates(request).TemplateResponse(
        request,
        "_run_status.html",
        {"run": rec},
        headers=headers,
    )
