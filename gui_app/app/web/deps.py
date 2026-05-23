"""Dependency-injection helpers used across routers.

These build per-request scoped objects (Database, Helper, etc.) bound
to the currently-active tenant id stored in the session cookie. By
funnelling every router through these we get one place that decides:
"is there a tenant set on this session, and what does it permit?"
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import Depends, HTTPException, Request, status

from database import Database
from batch_watermark_detector import BatchWatermarkDetector
from helpers import Helper
from tenancy.ids import validate_tenant_id, InvalidTenantError


def active_tenant(request: Request) -> Optional[str]:
    """Return the currently active tenant id from the session, or None.

    The session key matches what :func:`set_active_tenant` writes.
    """
    tid = request.session.get("tenant_id")
    if not tid:
        return None
    try:
        return validate_tenant_id(tid)
    except InvalidTenantError:
        request.session.pop("tenant_id", None)
        return None


def set_active_tenant(request: Request, tenant_id: Optional[str]) -> None:
    """Write the active tenant into the session, or clear it."""
    if not tenant_id:
        request.session.pop("tenant_id", None)
        return
    request.session["tenant_id"] = validate_tenant_id(tenant_id)


def require_tenant(request: Request) -> str:
    """Dependency: 400 if no tenant is set on this session."""
    tid = active_tenant(request)
    if not tid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active tenant. Pick one from the landing page first.",
        )
    return tid


def db(request: Request) -> Database:
    """Per-request Database bound to the active tenant.

    Constructs a fresh Database each call (cheap; the engine is
    cached at the SQLAlchemy level). When no tenant is set we still
    return a Database with no tenant so admin pages (which need to
    list tenants regardless of which one is "active") keep working.
    """
    return Database(tenant_id=active_tenant(request))


def helper(request: Request, db: Database = Depends(db)) -> Helper:
    tid = active_tenant(request)
    detector = BatchWatermarkDetector(db, os.getenv("OPENAI_API_KEY"))
    return Helper(db=db, detector=detector, tenant_id=tid)
