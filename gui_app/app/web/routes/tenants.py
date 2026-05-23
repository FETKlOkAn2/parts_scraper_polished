"""Tenant picker + admin page.

Two surfaces:

- ``GET  /``                landing. Tenant picker dropdown + the form
                            that kicks off a new run (covered in the
                            workflow router).
- ``POST /tenant``          set the active tenant on this session.
- ``GET  /tenants``         admin: list, edit, set quota, change status.
- ``POST /tenants``         upsert a tenant (registry row).
- ``POST /tenants/{id}/status``  change status.
- ``POST /tenants/{id}/quota``   set/clear quota.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from database import Database
from tenancy import TenantRegistry, VALID_STATUSES
from tenancy.ids import InvalidTenantError, validate_tenant_id

from ..deps import active_tenant, db as db_dep, set_active_tenant

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


def _registry(db: Database) -> TenantRegistry:
    return TenantRegistry(db)


# ---------- landing -----------------------------------------------------

@router.get("/", response_class=None)
def landing(request: Request, db: Database = Depends(db_dep)):
    """Tenant picker + the kick-off form for a run."""
    try:
        tenants = _registry(db).list()
    except Exception as e:
        # If the registry table doesn't exist yet (migration 004 not
        # applied) we render an empty picker plus a banner.
        tenants = []
        registry_error = str(e)
    else:
        registry_error = None

    return _templates(request).TemplateResponse(
        request,
        "landing.html",
        {
            "active_tenant": active_tenant(request),
            "tenants": tenants,
            "registry_error": registry_error,
            "valid_statuses": VALID_STATUSES,
        },
    )


@router.post("/tenant")
def select_tenant(request: Request, tenant_id: str = Form(...)):
    """Set the active tenant on this session and bounce home."""
    try:
        set_active_tenant(request, tenant_id)
    except InvalidTenantError as e:
        # Surface validation error on landing.
        request.session["flash"] = {"kind": "err", "msg": str(e)}
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    request.session["flash"] = {
        "kind": "ok",
        "msg": f"Active tenant set to {tenant_id}.",
    }
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/tenant/clear")
def clear_tenant(request: Request):
    set_active_tenant(request, None)
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


# ---------- admin -------------------------------------------------------

@router.get("/tenants", response_class=None)
def tenants_index(request: Request, db: Database = Depends(db_dep)):
    try:
        rows = _registry(db).list()
        error = None
    except Exception as e:
        rows = []
        error = str(e)
    return _templates(request).TemplateResponse(
        request,
        "tenants_admin.html",
        {
            "active_tenant": active_tenant(request),
            "tenants": rows,
            "error": error,
            "valid_statuses": VALID_STATUSES,
        },
    )


@router.post("/tenants")
def upsert_tenant(
    request: Request,
    tenant_id: str = Form(...),
    display_name: Optional[str] = Form(None),
    status_val: str = Form("active"),
    monthly_image_quota: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    db: Database = Depends(db_dep),
):
    try:
        validate_tenant_id(tenant_id)
        quota = int(monthly_image_quota) if monthly_image_quota else None
        _registry(db).upsert(
            tenant_id,
            display_name=display_name or None,
            status=status_val,
            monthly_image_quota=quota,
            notes=notes or None,
        )
    except (InvalidTenantError, ValueError) as e:
        request.session["flash"] = {"kind": "err", "msg": str(e)}
    else:
        request.session["flash"] = {
            "kind": "ok",
            "msg": f"Tenant {tenant_id} saved.",
        }
    return RedirectResponse("/tenants", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/tenants/{tenant_id}/status")
def change_status(
    request: Request,
    tenant_id: str,
    new_status: str = Form(...),
    db: Database = Depends(db_dep),
):
    try:
        _registry(db).set_status(tenant_id, new_status)
    except (InvalidTenantError, ValueError) as e:
        request.session["flash"] = {"kind": "err", "msg": str(e)}
    else:
        request.session["flash"] = {
            "kind": "ok",
            "msg": f"{tenant_id} → {new_status}",
        }
    return RedirectResponse("/tenants", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/tenants/{tenant_id}/quota")
def change_quota(
    request: Request,
    tenant_id: str,
    quota: str = Form(""),
    db: Database = Depends(db_dep),
):
    try:
        value = int(quota) if quota else None
        _registry(db).set_quota(tenant_id, value)
    except (InvalidTenantError, ValueError) as e:
        request.session["flash"] = {"kind": "err", "msg": str(e)}
    else:
        request.session["flash"] = {
            "kind": "ok",
            "msg": f"{tenant_id} quota updated.",
        }
    return RedirectResponse("/tenants", status_code=status.HTTP_303_SEE_OTHER)
