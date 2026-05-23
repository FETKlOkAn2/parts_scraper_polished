"""Web UI: runs detail + status partial + workflow gate."""
import base64
import datetime as dt
from unittest.mock import MagicMock

import pandas as pd
import pytest


@pytest.fixture
def app(monkeypatch):
    for k, v in {
        "AUTH_USERNAME": "test", "AUTH_PASSWORD": "test",
        "SECRET_KEY": "test-secret", "BUCKET": "test-bucket",
        "DB_HOST": "h", "DB_PORT": "1433", "DB_USER": "u", "DB_PASSWORD": "p",
        "OPENAI_API_KEY": "sk-test",
    }.items():
        monkeypatch.setenv(k, v)
    from web.main import create_app
    return create_app()


def _run_row(stage="search", **overrides):
    base = {
        "job_id": "20260523T120000-deadbeef",
        "tenant_id": "acme-parts",
        "operator": "test",
        "stage": stage,
        "csv_rows": 25,
        "progress_note": "doing things",
        "error": None,
        "report_html_url": None,
        "report_json_url": None,
        "manifest_url": None,
        "created_at": dt.datetime(2026, 5, 23, 12, 0, 0),
        "updated_at": dt.datetime(2026, 5, 23, 12, 5, 0),
        "completed_at": None,
    }
    base.update(overrides)
    return pd.DataFrame([base])


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def auth_client(app, mock_db):
    from fastapi.testclient import TestClient
    from web import deps
    app.dependency_overrides[deps.db] = lambda: mock_db
    c = TestClient(app)
    c.headers["Authorization"] = "Basic " + base64.b64encode(b"test:test").decode()
    return c


def test_run_detail_404_when_missing(auth_client, mock_db):
    mock_db.read_sql_query.return_value = pd.DataFrame()
    r = auth_client.get("/runs/nope")
    assert r.status_code == 404


def test_run_detail_shows_stage_pill(auth_client, mock_db):
    mock_db.read_sql_query.return_value = _run_row(stage="search")
    r = auth_client.get("/runs/20260523T120000-deadbeef")
    assert r.status_code == 200
    assert 'class="status-pill search"' in r.text


def test_status_partial_polls_when_not_terminal(auth_client, mock_db):
    mock_db.read_sql_query.return_value = _run_row(stage="search")
    r = auth_client.get("/runs/20260523T120000-deadbeef/status")
    assert r.status_code == 200
    # Non-terminal → has the htmx polling attribute.
    assert 'hx-trigger="every 5s"' in r.text
    # Non-terminal → no HX-Trigger header.
    assert "hx-trigger" not in r.headers


def test_status_partial_stops_polling_when_complete(auth_client, mock_db):
    mock_db.read_sql_query.return_value = _run_row(
        stage="complete",
        progress_note="all done",
        completed_at=dt.datetime(2026, 5, 23, 12, 30, 0),
    )
    r = auth_client.get("/runs/20260523T120000-deadbeef/status")
    assert r.status_code == 200
    # Terminal → no polling attribute on the status block.
    assert 'hx-trigger="every 5s"' not in r.text
    # Terminal → server tells HTMX so via header.
    assert r.headers.get("HX-Trigger") == "run-terminal"


def test_status_partial_shows_next_button_after_search_done(auth_client, mock_db):
    mock_db.read_sql_query.return_value = _run_row(
        stage="search",
        progress_note="search complete — click 'AI watermark' to continue",
    )
    r = auth_client.get("/runs/20260523T120000-deadbeef/status")
    assert 'action="/runs/20260523T120000-deadbeef/watermark"' in r.text


def test_status_partial_shows_resubmit_after_unusable(auth_client, mock_db):
    mock_db.read_sql_query.return_value = _run_row(
        stage="failed",
        error="2 batch(es) finished unusable — use 'Resubmit failed batches' on the run page",
    )
    r = auth_client.get("/runs/20260523T120000-deadbeef/status")
    assert 'action="/runs/20260523T120000-deadbeef/resubmit-failed"' in r.text


def test_run_start_requires_tenant(auth_client):
    """POST /run/start with no active tenant returns 400."""
    csv_bytes = b"number,description\nAB123,brake disc\n"
    r = auth_client.post(
        "/run/start",
        files={"csv": ("input.csv", csv_bytes, "text/csv")},
    )
    assert r.status_code == 400
    assert "No active tenant" in r.text


def test_run_start_rejects_bad_csv(auth_client):
    """Even with a tenant, a CSV missing required columns is 400."""
    # Set tenant first.
    auth_client.post("/tenant", data={"tenant_id": "acme-parts"})

    csv_bytes = b"foo,bar\nx,y\n"
    r = auth_client.post(
        "/run/start",
        files={"csv": ("input.csv", csv_bytes, "text/csv")},
    )
    assert r.status_code == 400
    assert "missing required column" in r.text
