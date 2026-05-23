"""Web UI: tenant picker + admin endpoints."""
import base64
from unittest.mock import MagicMock

import pandas as pd
import pytest


@pytest.fixture
def app(monkeypatch):
    for k, v in {
        "AUTH_USERNAME": "test",
        "AUTH_PASSWORD": "test",
        "SECRET_KEY": "test-secret",
        "BUCKET": "test-bucket",
        "DB_HOST": "h", "DB_PORT": "1433", "DB_USER": "u", "DB_PASSWORD": "p",
    }.items():
        monkeypatch.setenv(k, v)
    from web.main import create_app
    return create_app()


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.read_sql_query.return_value = pd.DataFrame()
    return db


@pytest.fixture
def auth_client(app, mock_db):
    from fastapi.testclient import TestClient
    from web import deps
    app.dependency_overrides[deps.db] = lambda: mock_db
    c = TestClient(app)
    c.headers["Authorization"] = "Basic " + base64.b64encode(b"test:test").decode()
    return c


def test_select_tenant_sets_session_cookie(auth_client):
    r = auth_client.post("/tenant", data={"tenant_id": "acme-parts"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    # The session cookie has been issued; the next GET should show the tenant.
    landing = auth_client.get("/")
    assert "acme-parts" in landing.text


def test_select_invalid_tenant_id_redirects_with_flash(auth_client):
    r = auth_client.post("/tenant", data={"tenant_id": "BAD TENANT"}, follow_redirects=False)
    assert r.status_code == 303
    # Follow to landing; the flash should surface the invalid-tenant error.
    landing = auth_client.get("/")
    assert "invalid tenant id" in landing.text.lower()


def test_clear_tenant_resets_session(auth_client):
    auth_client.post("/tenant", data={"tenant_id": "acme-parts"})
    auth_client.post("/tenant/clear")
    landing = auth_client.get("/")
    # No active tenant → run form should be hidden.
    assert "No tenant selected" in landing.text or "Start a run" not in landing.text


def test_upsert_tenant_calls_registry(auth_client, mock_db):
    """POST /tenants should hit MERGE dbo.tenants via execute_sql."""
    r = auth_client.post(
        "/tenants",
        data={
            "tenant_id": "acme-parts",
            "display_name": "Acme Parts",
            "status_val": "active",
            "monthly_image_quota": "5000",
            "notes": "test",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    # Registry's upsert calls execute_sql with a MERGE.
    assert mock_db.execute_sql.called
    sql = mock_db.execute_sql.call_args.args[0]
    assert "MERGE dbo.tenants" in sql


def test_upsert_tenant_rejects_bad_id(auth_client, mock_db):
    r = auth_client.post(
        "/tenants",
        data={
            "tenant_id": "BAD",
            "status_val": "active",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    # Should not have hit MERGE for the bad id.
    assert not mock_db.execute_sql.called


def test_set_status_invokes_update(auth_client, mock_db):
    r = auth_client.post(
        "/tenants/acme-parts/status",
        data={"new_status": "suspended"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    sql = mock_db.execute_sql.call_args.args[0]
    assert "UPDATE dbo.tenants" in sql
    assert "status = :status" in sql


def test_set_quota_clears_when_blank(auth_client, mock_db):
    auth_client.post(
        "/tenants/acme-parts/quota",
        data={"quota": ""},
        follow_redirects=False,
    )
    params = mock_db.execute_sql.call_args.kwargs["params"]
    assert params["q"] is None
