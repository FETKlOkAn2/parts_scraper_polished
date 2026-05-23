"""Liveness / readiness probes.

``/healthz`` is exempt from auth so an ALB or other LB can hit it.
It returns 200 unconditionally; deeper checks (DB reachable, S3
reachable) live in ``/readyz`` which DOES require auth.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz", include_in_schema=False)
def readyz(request: Request) -> dict:
    """Deeper readiness check. Currently a no-op besides reaching here
    (which proves auth + the app is up). When we want to gate ALB
    rollover on DB/S3 reachability, add the checks here."""
    return {"status": "ok"}
