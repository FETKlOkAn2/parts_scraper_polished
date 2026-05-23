"""JobRunner: spawn/track/cancel + orphan adoption on startup."""
import asyncio
from unittest.mock import MagicMock

import pytest


def test_job_runner_spawn_then_track(monkeypatch):
    monkeypatch.setenv("CUSTOMER", "test")
    from web.jobs import JobRunner

    async def _go():
        runner = JobRunner()
        done = asyncio.Event()

        async def _work():
            await asyncio.sleep(0.01)
            done.set()

        runner.spawn("job-1", lambda: _work())
        assert runner.is_running("job-1")
        await done.wait()
        # Give the wrap-finally a tick to remove it from the dict.
        await asyncio.sleep(0.01)
        assert not runner.is_running("job-1")

    asyncio.run(_go())


def test_job_runner_cancel(monkeypatch):
    monkeypatch.setenv("CUSTOMER", "test")
    from web.jobs import JobRunner

    async def _go():
        runner = JobRunner()
        started = asyncio.Event()

        async def _slow():
            started.set()
            await asyncio.sleep(10)

        runner.spawn("slow", lambda: _slow())
        await started.wait()
        assert runner.cancel("slow") is True
        await asyncio.sleep(0.01)
        # Cancel returns False for unknown / already-done.
        assert runner.cancel("slow") is False
        assert runner.cancel("never-existed") is False

    asyncio.run(_go())


def test_job_runner_swallows_exceptions(monkeypatch, capsys):
    monkeypatch.setenv("CUSTOMER", "test")
    from web.jobs import JobRunner

    async def _go():
        runner = JobRunner()

        async def _boom():
            raise RuntimeError("nope")

        runner.spawn("boom", lambda: _boom())
        await asyncio.sleep(0.05)
        assert not runner.is_running("boom")

    asyncio.run(_go())


def test_adopt_orphaned_runs_marks_non_terminal_as_failed():
    from web.jobs import adopt_orphaned_runs

    db = MagicMock()
    db.execute_sql.return_value = MagicMock(rowcount=3)
    count = adopt_orphaned_runs(db, restart_marker="x")
    assert count == 3
    sql = db.execute_sql.call_args.args[0]
    assert "UPDATE dbo.runs" in sql
    assert "N'failed'" in sql
    # Restricts to non-terminal stages only.
    assert "stage IN (N'queued', N'search', N'watermark', N'filter')" in sql


def test_adopt_orphaned_runs_fails_open_when_table_missing():
    from web.jobs import adopt_orphaned_runs
    db = MagicMock()
    db.execute_sql.side_effect = RuntimeError("Invalid object name 'dbo.runs'")
    # Must not raise; returns 0 so startup continues.
    assert adopt_orphaned_runs(db) == 0
