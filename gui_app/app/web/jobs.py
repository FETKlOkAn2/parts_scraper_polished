"""Background-task runner for the web operator console.

The Tkinter UI ran long stages inline on a background thread (one
process, one stage at a time, blocking the UI). The web UI inverts
that: each stage kick-off schedules an asyncio task on the running
event loop and returns immediately. The task updates ``dbo.runs``
as it progresses; the page polls /runs/{job_id}/status via HTMX.

Why asyncio over a real queue (Celery, RQ, SQS-of-our-own)?

- The stages are already SQS-fanned-out: the heavy work happens on
  EC2 workers, not in the web process. The web process just submits
  work and polls AWS for completion.
- A single uvicorn worker can comfortably hold the in-flight runs
  (operators run one or two concurrent jobs, not thousands).
- Zero new infra to deploy.

When this grows to "multiple operators running dozens of jobs from
different workstations", we'll move stage orchestration to a proper
queue with workers, and the web process becomes a thin status reader.

The runner is intentionally fire-and-forget. If the web process
restarts mid-run, the stage's underlying AWS work keeps running
(workers are stateless, batches don't care who polls them); on
restart we mark any non-terminal run as 'failed' with a "process
restart" note via :func:`adopt_orphaned_runs`.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Awaitable, Callable

from obs import get_logger

_log = get_logger("web.jobs")


class JobRunner:
    """Schedules and tracks asyncio tasks for stage execution.

    One instance per FastAPI app; held at ``app.state.jobs``.
    """

    def __init__(self):
        self._tasks: dict[str, asyncio.Task] = {}
        self._lock = threading.Lock()

    def spawn(self, job_id: str, coro_factory: Callable[[], Awaitable[None]]) -> None:
        """Schedule ``coro_factory()`` to run in the background.

        ``coro_factory`` is a no-arg callable that returns the
        coroutine; we accept a factory rather than the coroutine
        itself so tests can pass a sync function that immediately
        completes.
        """
        loop = asyncio.get_event_loop()
        task = loop.create_task(self._wrap(job_id, coro_factory()))
        with self._lock:
            self._tasks[job_id] = task

    def is_running(self, job_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(job_id)
        return task is not None and not task.done()

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(job_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    async def _wrap(self, job_id: str, coro: Awaitable[None]) -> None:
        try:
            await coro
        except asyncio.CancelledError:
            _log.info("background job cancelled", job_id=job_id)
            raise
        except Exception:
            _log.exception("background job failed", job_id=job_id)
        finally:
            with self._lock:
                self._tasks.pop(job_id, None)


def adopt_orphaned_runs(db, *, restart_marker: str = "uvicorn restart") -> int:
    """Mark every non-terminal run as failed.

    Called once on web app startup. A run that was 'search'/'watermark'/
    'filter' when the web process died has lost its in-process task;
    the underlying AWS work might still be ongoing but we can't track
    it. Marking failed gives the operator a clean state to resubmit
    from.
    """
    try:
        result = db.execute_sql(
            """
            UPDATE dbo.runs
            SET stage = N'failed',
                error = :marker,
                updated_at = SYSUTCDATETIME(),
                completed_at = SYSUTCDATETIME()
            WHERE stage IN (N'queued', N'search', N'watermark', N'filter');
            """,
            params={"marker": restart_marker},
        )
        rowcount = getattr(result, "rowcount", 0) or 0
        if rowcount:
            _log.info("adopted orphaned runs", count=rowcount, marker=restart_marker)
        return rowcount
    except Exception as e:
        # If the runs table doesn't exist (migration 006 not applied),
        # don't crash startup. Just log and continue.
        _log.warning("could not adopt orphaned runs", error=str(e))
        return 0
