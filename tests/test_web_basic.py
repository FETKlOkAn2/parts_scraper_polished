"""Web UI: auth + smoke tests for every top-level page.

We use FastAPI's TestClient with the ``db`` dependency overridden to
a MagicMock — no real SQL Server, no real S3.
"""
import base64
import os
from unittest.mock import MagicMock

import pandas as pd
import pytest


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("AUTH_USERNAME", "test")
    monkeypatch.setenv("AUTH_PASSWORD", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("BUCKET", "test-bucket")
    # Database constructor uses these. We don't connect; only env parse.
    monkeypatch.setenv("DB_HOST", "h")
    monkeypatch.setenv("DB_PORT", "1433")
    monkeypatch.setenv("DB_USER", "u")
    monkeypatch.setenv("DB_PASSWORD", "p")

    from web.main import create_app
    return create_app()


@pytest.fixture
def mock_db():
    db = MagicMock()
    # Default to empty frames so list pages render with empty-state.
    db.read_sql_query.return_value = pd.DataFrame()
    return db


@pytest.fixture
def client(app, mock_db):
    from fastapi.testclient import TestClient
    from web import deps
    app.dependency_overrides[deps.db] = lambda: mock_db
    c = TestClient(app)
    return c


@pytest.fixture
def auth_client(client):
    client.headers["Authorization"] = "Basic " + base64.b64encode(b"test:test").decode()
    return client


# ---- auth ----------------------------------------------------------------

def test_healthz_bypasses_auth(client):
    r = client.get("/healthz")
    assert r.status_code == 200


def test_root_requires_auth(client):
    r = client.get("/")
    assert r.status_code == 401
    assert r.headers["www-authenticate"].startswith("Basic ")


def test_wrong_creds_rejected(client):
    client.headers["Authorization"] = "Basic " + base64.b64encode(b"bad:bad").decode()
    r = client.get("/")
    assert r.status_code == 401


def test_malformed_basic_header_rejected(client):
    client.headers["Authorization"] = "NotBasic foo"
    r = client.get("/")
    assert r.status_code == 401


def test_no_colon_in_basic_header_rejected(client):
    client.headers["Authorization"] = "Basic " + base64.b64encode(b"justuser").decode()
    r = client.get("/")
    assert r.status_code == 401


# ---- smoke -----------------------------------------------------------

@pytest.mark.parametrize("path", ["/", "/tenants", "/runs", "/reports", "/provenance"])
def test_pages_render_under_auth(auth_client, path):
    r = auth_client.get(path)
    assert r.status_code == 200, r.text[:300]
    assert "<title>" in r.text
    assert "operator console" in r.text.lower()


def test_tenant_picker_form_uses_post(auth_client):
    r = auth_client.get("/")
    assert 'action="/tenant"' in r.text
    assert 'method="post"' in r.text


def test_provenance_empty_search_returns_no_rows_section(auth_client):
    r = auth_client.get("/provenance")
    # No query yet → no results table, just the form.
    assert "Search" in r.text
    assert "No provenance rows found." not in r.text


def test_provenance_search_with_query_runs_sql(auth_client, mock_db):
    mock_db.read_sql_query.return_value = pd.DataFrame()
    r = auth_client.get("/provenance?part_number=AB123")
    assert r.status_code == 200
    # Hit the SQL path
    assert mock_db.read_sql_query.called
    # Empty result shows the "No provenance rows found" hint
    assert "No provenance rows found." in r.text
