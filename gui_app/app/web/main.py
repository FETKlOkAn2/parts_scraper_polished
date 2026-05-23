"""FastAPI entry point for the operator web console.

The app is composed of a small set of router modules under
``web/routes/``; ``main`` just wires them up, mounts static files,
and installs the auth + observability middleware.

Configuration is via environment variables:

- ``AUTH_USERNAME``, ``AUTH_PASSWORD`` — basic-auth credentials for
  the operator. Both required; if either is unset the app refuses to
  start (a publicly-reachable operator console with no auth is the
  single failure mode we never want).
- ``SECRET_KEY`` — used to sign session cookies. Defaults to a
  warning-and-derive value for local dev; required to be set
  explicitly in production.
- ``BUCKET``, ``DEFAULT_TENANT_ID``, etc. — same as the rest of the
  apps.
"""
from __future__ import annotations

import contextlib
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from obs import get_logger

from .auth import BasicAuthMiddleware
from .jobs import JobRunner, adopt_orphaned_runs
from .routes import health, tenants, runs, workflow, reports

_log = get_logger("web.app")

PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = PACKAGE_ROOT / "templates"
STATIC_DIR = PACKAGE_ROOT / "static"


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"environment variable {name!r} is required to start the web console"
        )
    return value


def create_app() -> FastAPI:
    """Build and return the FastAPI app.

    Exposed as a factory rather than a module-level instance so tests
    can build the app with overridden config and the production
    deployment can rebuild it without process restarts (e.g. after
    rotating creds).
    """
    auth_user = _required_env("AUTH_USERNAME")
    auth_pass = _required_env("AUTH_PASSWORD")
    secret_key = os.environ.get("SECRET_KEY") or _required_env("SECRET_KEY")

    @contextlib.asynccontextmanager
    async def _lifespan(_app: FastAPI):
        # Startup: adopt any non-terminal runs orphaned by a previous
        # process. fail-open if the table doesn't exist.
        try:
            from database import Database
            adopt_orphaned_runs(Database())
        except Exception as e:
            _log.warning("startup adopt skipped", error=str(e))
        yield
        # Shutdown: no work to do — background tasks run on the same
        # event loop and are torn down by uvicorn.

    app = FastAPI(
        title="Parts pipeline · operator console",
        description=(
            "Operator UI for the multi-tenant parts image pipeline. "
            "Replaces the Tkinter desktop GUI."
        ),
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=_lifespan,
    )

    # Session cookie. The session carries the operator's currently-
    # active tenant id; no business data lives in it.
    app.add_middleware(SessionMiddleware, secret_key=secret_key)

    # Basic auth — outside of the session middleware so the cookie
    # isn't even issued until the operator has authenticated.
    app.add_middleware(
        BasicAuthMiddleware,
        username=auth_user,
        password=auth_pass,
        # Health checks bypass auth so an ALB can hit them.
        public_paths=("/healthz", "/static/"),
    )

    # Static files (CSS, the HTMX runtime, a small favicon).
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Templates shared across routers.
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.templates = templates

    # Background job runner. One instance per app.
    app.state.jobs = JobRunner()

    # Routers — one per logical surface.
    app.include_router(health.router)
    app.include_router(tenants.router)
    app.include_router(runs.router)
    app.include_router(workflow.router)
    app.include_router(reports.router)

    _log.info("web app initialised", auth_user=auth_user)
    return app


# Allow `uvicorn web.main:app` directly.
app = create_app()
