"""Operator workflow endpoints.

The web UI's version of what the Tkinter GUI's ``search_images`` /
``perform_watermark`` / ``perform_filter`` did. Each stage is a POST
endpoint that:

  1. validates the active tenant (and quota gate on /run/start)
  2. creates or updates the dbo.runs row
  3. schedules the actual work as an asyncio background task
  4. returns a redirect to the run status page

The status page (phase 5) polls /runs/{job_id}/status every 5s via
HTMX to display progress.

The background tasks call the same Helper methods that the Tkinter
GUI does; nothing about the SQS / EC2 / OpenAI / SQL contract changes.
"""
from __future__ import annotations

import asyncio
import io
import os
import time
from typing import Optional

import pandas as pd
from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status,
)
from fastapi.responses import RedirectResponse

from database import Database
from helpers import Helper
from report_builder import ReportBuilder, RunSummary, new_job_id
from tenancy import RunsRepository, TenantRegistry

from ..deps import active_tenant, db as db_dep, helper as helper_dep, require_tenant

router = APIRouter()


def _runs(db: Database) -> RunsRepository:
    return RunsRepository(db)


def _bucket() -> str:
    bucket = os.getenv("BUCKET")
    if not bucket:
        raise RuntimeError("BUCKET env var is required")
    return bucket


# ---------- /run/start --------------------------------------------------

@router.post("/run/start")
async def run_start(
    request: Request,
    csv: UploadFile = File(...),
    tenant_id: str = Depends(require_tenant),
    db: Database = Depends(db_dep),
    helper: Helper = Depends(helper_dep),
):
    """Receive a CSV, register a new run, and kick off the image-search stage."""

    # 1. Parse CSV up front so we can fail fast (bad encoding, missing
    #    columns) before we spin a background task.
    raw = await csv.read()
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as e:
        raise HTTPException(400, detail=f"CSV parse error: {e}")

    expected = {"number", "description"}
    missing = expected - set(df.columns)
    if missing:
        raise HTTPException(
            400,
            detail=f"CSV missing required column(s): {sorted(missing)}",
        )
    csv_rows = int(len(df))

    # 2. Quota gate via the tenant registry — refuse before we touch
    #    SQL/S3 if the tenant is suspended or over quota.
    try:
        ok, reason = TenantRegistry(db).check_quota(tenant_id, would_add=csv_rows)
        if not ok:
            raise HTTPException(409, detail=f"Tenant gate refused run: {reason}")
    except HTTPException:
        raise
    except Exception:
        # Registry table missing → fail-open (single-tenant deployments
        # that haven't run migration 004).
        pass

    # 3. Allocate job_id and create the runs row.
    job_id = new_job_id()
    _runs(db).create(
        job_id=job_id,
        tenant_id=tenant_id,
        operator=os.environ.get("AUTH_USERNAME"),
        csv_rows=csv_rows,
    )

    # 4. Schedule the background stage. We capture bucket + tenant
    #    locally so the closure doesn't need request-scoped state.
    bucket = _bucket()

    async def _run_search_stage():
        await asyncio.to_thread(_search_stage_sync, job_id, tenant_id, df, bucket)

    request.app.state.jobs.spawn(job_id, lambda: _run_search_stage())

    # 5. Redirect to the status page (phase 5).
    return RedirectResponse(f"/runs/{job_id}", status_code=status.HTTP_303_SEE_OTHER)


# ---------- /runs/{job_id}/watermark + /filter + /resubmit -------------

@router.post("/runs/{job_id}/watermark")
async def run_watermark(
    request: Request,
    job_id: str,
    tenant_id: str = Depends(require_tenant),
):
    bucket = _bucket()

    async def _stage():
        await asyncio.to_thread(_watermark_stage_sync, job_id, tenant_id, bucket)

    request.app.state.jobs.spawn(job_id, lambda: _stage())
    return RedirectResponse(f"/runs/{job_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/runs/{job_id}/filter")
async def run_filter(
    request: Request,
    job_id: str,
    tenant_id: str = Depends(require_tenant),
):
    bucket = _bucket()

    async def _stage():
        await asyncio.to_thread(_filter_stage_sync, job_id, tenant_id, bucket)

    request.app.state.jobs.spawn(job_id, lambda: _stage())
    return RedirectResponse(f"/runs/{job_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/runs/{job_id}/resubmit-failed")
async def run_resubmit_failed(
    request: Request,
    job_id: str,
    tenant_id: str = Depends(require_tenant),
):
    bucket = _bucket()

    async def _stage():
        await asyncio.to_thread(_resubmit_stage_sync, job_id, tenant_id, bucket)

    request.app.state.jobs.spawn(job_id, lambda: _stage())
    return RedirectResponse(f"/runs/{job_id}", status_code=status.HTTP_303_SEE_OTHER)


# ---------- stage bodies (synchronous; run via asyncio.to_thread) -------

def _search_stage_sync(job_id: str, tenant_id: str, df: pd.DataFrame, bucket: str):
    """Image-search stage. Mirrors PartsScraperGUI.search_images."""
    db = Database(tenant_id=tenant_id)
    runs = _runs(db)
    runs.set_stage(job_id, "search", progress_note="uploading CSV to dbo.parts")

    try:
        # 1. Upsert into dbo.parts.
        db.upsert_append_new_only(df, target="dbo.parts")

        # 2. Identify pending parts.
        runs.set_stage(job_id, "search", progress_note="identifying pending parts")
        pending = db.read_sql_query(
            "SELECT number, description FROM dbo.parts "
            "WHERE tenant_id = :t AND final_tag IS NULL;",
            params={"t": tenant_id},
        )

        # 3. Shard + push to SQS.
        max_rows = int(os.getenv("MAX_ROWS_PER_RUN", "25"))
        chunk_size = int(os.getenv("SEARCH_CHUNK_SIZE", "5"))
        pending = pending.iloc[:max_rows]

        from helpers import Helper
        from batch_watermark_detector import BatchWatermarkDetector
        detector = BatchWatermarkDetector(db, os.getenv("OPENAI_API_KEY"))
        helper = Helper(db=db, detector=detector, tenant_id=tenant_id)

        runs.set_stage(job_id, "search", progress_note=f"sharding {len(pending)} parts")
        num_chunks = helper.split_data_and_upload_jobs(
            df=pending,
            bucket=bucket,
            prefix=os.getenv("SEARCH_KEY", "search_jobs"),
            chunk_size=chunk_size,
        )

        runs.set_stage(job_id, "search", progress_note=f"enqueued {num_chunks} shards")
        helper.send_chunk_messages(
            job_id=job_id,
            queue_url=os.getenv("SEARCH_QUEUE_URL"),
            num_chunks=num_chunks,
            key=os.getenv("SEARCH_KEY", "search_jobs"),
        )

        # 4. Wait for EC2 workers to drain.
        _wait_for_instances(runs, job_id, helper)

        # 5. Clean up the job CSVs and mark stage waiting on operator.
        db.empty_prefix(bucket, os.getenv("SEARCH_KEY", "search_jobs"))
        runs.set_stage(
            job_id,
            "search",
            progress_note="search complete — click 'AI watermark' to continue",
        )
    except Exception as e:
        runs.set_error(job_id, f"search stage failed: {e}")
        raise


def _watermark_stage_sync(job_id: str, tenant_id: str, bucket: str):
    from batch_watermark_detector import BatchUnusableError

    db = Database(tenant_id=tenant_id)
    runs = _runs(db)
    runs.set_stage(job_id, "watermark", progress_note="building OpenAI batches")

    from helpers import Helper
    from batch_watermark_detector import BatchWatermarkDetector
    detector = BatchWatermarkDetector(db, os.getenv("OPENAI_API_KEY"))
    helper = Helper(db=db, detector=detector, tenant_id=tenant_id)

    try:
        batch_ids, batch_map = helper.organize_and_submit_batch() or ([], {})
        if not batch_ids:
            runs.set_stage(job_id, "watermark", progress_note="no candidates to classify")
            return

        # Store the batch_map on the run row's progress note for the
        # resubmit-failed flow.
        runs.set_stage(
            job_id, "watermark",
            progress_note=f"submitted {len(batch_ids)} batches; polling",
        )

        # Persist the batch map so /resubmit-failed can find it.
        _store_batch_map(db, job_id, batch_map)

        # Poll until terminal.
        _poll_openai_batches(runs, job_id, helper, batch_ids)

        # Parse results — raises BatchUnusableError on any non-OK batch.
        try:
            helper.parse_ai_results(batch_ids, batch_map=batch_map)
        except BatchUnusableError as e:
            unusable = getattr(e, "unusable", [])
            resubmit_map = getattr(e, "resubmit_map", {})
            _store_resubmit_map(db, job_id, resubmit_map)
            runs.set_error(
                job_id,
                f"{len(unusable)} batch(es) finished unusable — "
                f"use 'Resubmit failed batches' on the run page",
            )
            return

        db.send_delete_request_watermark()
        runs.set_stage(
            job_id, "watermark",
            progress_note="watermark complete — click 'Filter' to continue",
        )
    except BatchUnusableError:
        raise  # already handled above
    except Exception as e:
        runs.set_error(job_id, f"watermark stage failed: {e}")
        raise


def _filter_stage_sync(job_id: str, tenant_id: str, bucket: str):
    db = Database(tenant_id=tenant_id)
    runs = _runs(db)
    runs.set_stage(job_id, "filter", progress_note="gathering candidate images")

    from helpers import Helper
    from batch_watermark_detector import BatchWatermarkDetector
    detector = BatchWatermarkDetector(db, os.getenv("OPENAI_API_KEY"))
    helper = Helper(db=db, detector=detector, tenant_id=tenant_id)

    try:
        all_data = db.read_sql_query(
            "SELECT tag_value FROM dbo.part_tags "
            "WHERE tenant_id = :t ORDER BY tag_value ASC;",
            params={"t": tenant_id},
        )

        runs.set_stage(job_id, "filter", progress_note="sharding into proc jobs")
        chunk_size = int(os.getenv("PROC_CHUNK_SIZE", "10"))
        num_chunks = helper.split_group_upload(
            df=all_data,
            bucket=bucket,
            prefix=os.getenv("PROC_KEY", "proc_jobs"),
            chunk_size=chunk_size,
        )

        runs.set_stage(job_id, "filter", progress_note=f"enqueued {num_chunks} proc shards")
        helper.send_chunk_messages(
            job_id=job_id,
            queue_url=os.getenv("PROC_QUEUE_URL"),
            num_chunks=num_chunks,
            key=os.getenv("PROC_KEY", "proc_jobs"),
        )

        _wait_for_instances(runs, job_id, helper)

        db.empty_prefix(bucket, os.getenv("PROC_KEY", "proc_jobs"))

        # Build and ship the run report.
        runs.set_stage(job_id, "filter", progress_note="building run report")
        _build_report(db, runs, job_id, tenant_id, bucket)

        # Clean state.
        db.execute_sql(
            "DELETE FROM dbo.part_tags WHERE tenant_id = :t;",
            params={"t": tenant_id},
        )
        db.empty_prefix(bucket, "images")
        runs.set_stage(job_id, "complete", progress_note="all stages complete")
    except Exception as e:
        runs.set_error(job_id, f"filter stage failed: {e}")
        raise


def _resubmit_stage_sync(job_id: str, tenant_id: str, bucket: str):
    db = Database(tenant_id=tenant_id)
    runs = _runs(db)
    failed_map = _load_resubmit_map(db, job_id)
    if not failed_map:
        runs.set_stage(job_id, "watermark", progress_note="nothing to resubmit")
        return

    from helpers import Helper
    from batch_watermark_detector import BatchWatermarkDetector
    detector = BatchWatermarkDetector(db, os.getenv("OPENAI_API_KEY"))
    helper = Helper(db=db, detector=detector, tenant_id=tenant_id)

    runs.set_stage(
        job_id, "watermark",
        progress_note=f"resubmitting {len(failed_map)} failed batch(es)",
    )
    try:
        new_ids, new_map = helper.resubmit_failed_batches(failed_map)
        if not new_ids:
            runs.set_error(job_id, "no batches were resubmitted (input files missing)")
            return
        _store_batch_map(db, job_id, new_map)
        _store_resubmit_map(db, job_id, {})  # clear the failed map
        runs.set_stage(
            job_id, "watermark",
            progress_note=f"resubmitted; polling {len(new_ids)} new batches",
        )
        _poll_openai_batches(runs, job_id, helper, new_ids)

        from batch_watermark_detector import BatchUnusableError
        try:
            helper.parse_ai_results(new_ids, batch_map=new_map)
        except BatchUnusableError as e:
            unusable = getattr(e, "unusable", [])
            resubmit_map = getattr(e, "resubmit_map", {})
            _store_resubmit_map(db, job_id, resubmit_map)
            runs.set_error(
                job_id,
                f"{len(unusable)} batch(es) still unusable after resubmit",
            )
            return

        db.send_delete_request_watermark()
        runs.set_stage(
            job_id, "watermark",
            progress_note="resubmit succeeded — click 'Filter' to continue",
        )
    except Exception as e:
        runs.set_error(job_id, f"resubmit failed: {e}")
        raise


# ---------- helpers ----------------------------------------------------

def _wait_for_instances(runs, job_id, helper, *, poll_secs: float = 60.0):
    """Block until every EC2 instance for this fleet is terminated.

    Mirrors the Tkinter loop in perform_filter / search_images. We
    update progress_note every minute so the status page has
    something to display.
    """
    elapsed = 0
    while True:
        time.sleep(poll_secs)
        elapsed += int(poll_secs)
        all_terminated, state = helper.determine_instance_state()
        runs.set_stage(
            job_id, _current_stage(runs, job_id),
            progress_note=f"waiting for workers ({state}); elapsed {elapsed // 60} min",
        )
        if all_terminated:
            return


def _poll_openai_batches(runs, job_id, helper, batch_ids, *, poll_secs: float = 60.0):
    """Block until every OpenAI batch reaches a terminal status."""
    time.sleep(40)  # initial delay before first poll, matches Tkinter behaviour
    minutes = 0
    while True:
        time.sleep(poll_secs)
        minutes += 1
        all_done = True
        statuses = []
        for bid in batch_ids:
            done, status_val = helper.detector.poll_multiple_batch_completion(bid)
            statuses.append(f"{bid}: {status_val}")
            if not done:
                all_done = False
        runs.set_stage(
            job_id, "watermark",
            progress_note=f"OpenAI poll #{minutes} — " + "; ".join(statuses)[:400],
        )
        if all_done:
            return


def _current_stage(runs, job_id) -> str:
    rec = runs.get(job_id)
    return rec.stage if rec else "queued"


def _build_report(db, runs, job_id, tenant_id, bucket):
    """Trim version of the Tkinter perform_filter close-out."""
    try:
        row = db.read_sql_query(
            "SELECT COUNT(*) AS n FROM dbo.parts "
            "WHERE tenant_id = :t AND final_tag IS NOT NULL;",
            params={"t": tenant_id},
        )
        final_count = int(row["n"].iat[0])
    except Exception:
        final_count = 0

    samples = []
    try:
        sample_rows = db.read_sql_query(
            "SELECT TOP 12 number, description, final_tag "
            "FROM dbo.parts WHERE tenant_id = :t AND final_tag IS NOT NULL "
            "ORDER BY part_id DESC;",
            params={"t": tenant_id},
        )
        samples = [
            {
                "part_number": str(r["number"]),
                "description": str(r.get("description", "") or ""),
                "final_url": str(r["final_tag"]),
            }
            for _, r in sample_rows.iterrows()
        ]
    except Exception:
        pass

    import datetime as dt
    summary = RunSummary(
        job_id=job_id,
        customer=os.environ.get("CUSTOMER", "unknown"),
        tenant_id=tenant_id,
        started_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
        finished_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
        final_images_written=final_count,
    )
    try:
        refs = ReportBuilder(bucket=bucket).write(summary, samples=samples)
        runs.set_report_urls(job_id, refs["html_url"], refs["json_url"])
    except Exception as e:
        runs.set_stage(
            job_id, "filter",
            progress_note=f"report generation failed: {e}",
        )


# ---- tiny json blob storage on the run row (progress_note overflow) ----
# We keep failed_batch_resubmit_map and batch_map as JSON in S3 next
# to the run report. SQL columns stay narrow; the maps stay queryable
# enough for the status page.

def _store_batch_map(db, job_id, batch_map):
    _store_json_blob(db, job_id, "batch_map", batch_map)


def _store_resubmit_map(db, job_id, resubmit_map):
    _store_json_blob(db, job_id, "resubmit_map", resubmit_map)


def _load_resubmit_map(db, job_id) -> dict:
    return _load_json_blob(db, job_id, "resubmit_map") or {}


def _store_json_blob(db, job_id, kind, data):
    import json
    bucket = os.environ.get("BUCKET")
    if not bucket:
        return
    key = f"tenants/{db.tenant_id}/runs/{job_id}/{kind}.json"
    try:
        db.s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(data, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
    except Exception:
        pass


def _load_json_blob(db, job_id, kind) -> Optional[dict]:
    import json
    bucket = os.environ.get("BUCKET")
    if not bucket:
        return None
    key = f"tenants/{db.tenant_id}/runs/{job_id}/{kind}.json"
    try:
        resp = db.s3.get_object(Bucket=bucket, Key=key)
        return json.loads(resp["Body"].read().decode("utf-8"))
    except Exception:
        return None
