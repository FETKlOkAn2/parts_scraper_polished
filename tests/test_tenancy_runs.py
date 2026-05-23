"""RunsRepository: shape of INSERT / UPDATE statements."""
import datetime as dt
from unittest.mock import MagicMock

import pandas as pd
import pytest

from tenancy import RunsRepository, VALID_STAGES, TERMINAL_STAGES
from tenancy.runs import RunRecord


@pytest.fixture
def db():
    return MagicMock()


def test_create_inserts_with_queued_stage(db):
    RunsRepository(db).create(
        job_id="20260523T120000-x",
        tenant_id="acme",
        operator="alice",
        csv_rows=25,
    )
    sql = db.execute_sql.call_args.args[0]
    assert "INSERT INTO dbo.runs" in sql
    assert "N'queued'" in sql
    p = db.execute_sql.call_args.kwargs["params"]
    assert p["tenant_id"] == "acme"
    assert p["operator"] == "alice"
    assert p["csv_rows"] == 25


def test_create_validates_tenant_id(db):
    from tenancy.ids import InvalidTenantError
    with pytest.raises(InvalidTenantError):
        RunsRepository(db).create(job_id="x", tenant_id="BAD")


def test_set_stage_updates_progress(db):
    RunsRepository(db).set_stage("job-1", "search", progress_note="downloading")
    sql = db.execute_sql.call_args.args[0]
    assert "UPDATE dbo.runs" in sql
    assert "stage = :stage" in sql
    assert "progress_note = :progress_note" in sql
    # Non-terminal stage → no completed_at clause.
    assert "completed_at = SYSUTCDATETIME()" not in sql


def test_set_stage_to_terminal_stamps_completed_at(db):
    RunsRepository(db).set_stage("job-1", "complete")
    sql = db.execute_sql.call_args.args[0]
    assert "completed_at = SYSUTCDATETIME()" in sql


def test_set_stage_rejects_unknown(db):
    with pytest.raises(ValueError, match="unknown stage"):
        RunsRepository(db).set_stage("job-1", "frozen")


def test_set_error_marks_failed_and_stamps_completed(db):
    RunsRepository(db).set_error("job-1", "boom")
    sql = db.execute_sql.call_args.args[0]
    assert "N'failed'" in sql
    assert "error = :error" in sql
    assert "completed_at = SYSUTCDATETIME()" in sql


def test_get_returns_none_when_missing(db):
    db.read_sql_query.return_value = pd.DataFrame()
    assert RunsRepository(db).get("nope") is None


def test_get_returns_record(db):
    db.read_sql_query.return_value = pd.DataFrame([{
        "job_id": "job-1",
        "tenant_id": "acme",
        "operator": "alice",
        "stage": "search",
        "csv_rows": 25,
        "progress_note": "hi",
        "error": None,
        "report_html_url": None,
        "report_json_url": None,
        "manifest_url": None,
        "created_at": dt.datetime(2026, 5, 23),
        "updated_at": dt.datetime(2026, 5, 23, 12),
        "completed_at": None,
    }])
    rec = RunsRepository(db).get("job-1")
    assert isinstance(rec, RunRecord)
    assert rec.tenant_id == "acme"
    assert rec.stage == "search"
    assert rec.is_terminal is False
    assert rec.manifest_url is None


def test_set_manifest_url_updates_run(db):
    RunsRepository(db).set_manifest_url("job-1", "https://signed/manifest.csv")
    sql = db.execute_sql.call_args.args[0]
    assert "UPDATE dbo.runs" in sql
    assert "manifest_url = :manifest_url" in sql
    p = db.execute_sql.call_args.kwargs["params"]
    assert p["job_id"] == "job-1"
    assert p["manifest_url"] == "https://signed/manifest.csv"


def test_record_with_manifest_url_round_trips(db):
    db.read_sql_query.return_value = pd.DataFrame([{
        "job_id": "job-1",
        "tenant_id": "acme",
        "operator": None,
        "stage": "complete",
        "csv_rows": 100,
        "progress_note": "done",
        "error": None,
        "report_html_url": "https://signed/html",
        "report_json_url": "https://signed/json",
        "manifest_url": "https://signed/manifest.csv",
        "created_at": dt.datetime(2026, 5, 23),
        "updated_at": dt.datetime(2026, 5, 23, 12),
        "completed_at": dt.datetime(2026, 5, 23, 12, 30),
    }])
    rec = RunsRepository(db).get("job-1")
    assert rec.manifest_url == "https://signed/manifest.csv"


def test_record_is_terminal_for_complete_and_failed():
    base = dict(
        job_id="x", tenant_id="acme", operator=None, csv_rows=None,
        progress_note=None, error=None,
        report_html_url=None, report_json_url=None, manifest_url=None,
        created_at=None, updated_at=None, completed_at=None,
    )
    assert RunRecord(stage="complete", **base).is_terminal is True
    assert RunRecord(stage="failed", **base).is_terminal is True
    assert RunRecord(stage="search", **base).is_terminal is False


def test_list_recent_filters_by_tenant(db):
    db.read_sql_query.return_value = pd.DataFrame()
    RunsRepository(db).list_recent(tenant_id="acme", limit=10)
    sql = db.read_sql_query.call_args.args[0]
    assert "WHERE tenant_id = :tenant_id" in sql
    p = db.read_sql_query.call_args.kwargs["params"]
    assert p["tenant_id"] == "acme"
    assert p["n"] == 10


def test_list_recent_no_tenant_returns_all(db):
    db.read_sql_query.return_value = pd.DataFrame()
    RunsRepository(db).list_recent()
    sql = db.read_sql_query.call_args.args[0]
    assert "WHERE tenant_id" not in sql


def test_valid_stages_constant_includes_expected():
    assert "queued" in VALID_STAGES
    assert "search" in VALID_STAGES
    assert "watermark" in VALID_STAGES
    assert "filter" in VALID_STAGES
    assert "complete" in TERMINAL_STAGES
    assert "failed" in TERMINAL_STAGES
