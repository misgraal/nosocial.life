from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.security.sesions import get_user_id
from app.services.admin import (
    delete_user_account,
    get_admin_dashboard,
    revoke_file_share,
    revoke_folder_share,
    set_user_storage_quota,
    toggle_user_blocked,
    toggle_user_role,
    update_active_upload_disks,
)


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/admin")
async def main(request: Request, tab: str = "users", error: str | None = None, inspect_user: int | None = None):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if not user_id:
        return RedirectResponse("/", status_code=303)

    try:
        dashboard = await get_admin_dashboard(user_id, inspect_user)
    except ValueError:
        return RedirectResponse("/app/home", status_code=303)

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "current_tab": tab if tab in {"users", "access", "disk", "audit"} else "users",
            "error": error,
            "current_user": dashboard.current_user,
            "stats": dashboard.stats,
            "users": dashboard.users,
            "disks": dashboard.disks,
            "audit_logs": dashboard.audit_logs,
            "share_items": dashboard.share_items,
            "inspected_user": dashboard.inspected_user,
            "inspected_items": dashboard.inspected_items,
        }
    )


@router.post("/admin/users/{target_user_id}/toggle-role")
async def toggleUserRole(request: Request, target_user_id: int):
    sid = request.cookies.get("session_id")
    admin_user_id = get_user_id(sid)
    if not admin_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        await toggle_user_role(admin_user_id, target_user_id)
        return RedirectResponse("/admin?tab=users", status_code=303)
    except ValueError as error:
        return RedirectResponse(f"/admin?tab=users&error={str(error)}", status_code=303)


@router.post("/admin/users/{target_user_id}/delete")
async def deleteUser(request: Request, target_user_id: int):
    sid = request.cookies.get("session_id")
    admin_user_id = get_user_id(sid)
    if not admin_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        await delete_user_account(admin_user_id, target_user_id)
        return RedirectResponse("/admin?tab=users", status_code=303)
    except ValueError as error:
        return RedirectResponse(f"/admin?tab=users&error={str(error)}", status_code=303)


@router.post("/admin/users/{target_user_id}/toggle-block")
async def toggleUserBlocked(request: Request, target_user_id: int):
    sid = request.cookies.get("session_id")
    admin_user_id = get_user_id(sid)
    if not admin_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        await toggle_user_blocked(admin_user_id, target_user_id)
        return RedirectResponse("/admin?tab=users", status_code=303)
    except ValueError as error:
        return RedirectResponse(f"/admin?tab=users&error={str(error)}", status_code=303)


@router.post("/admin/users/{target_user_id}/quota")
async def updateUserQuota(request: Request, target_user_id: int, storage_quota_gb: str = Form(...)):
    sid = request.cookies.get("session_id")
    admin_user_id = get_user_id(sid)
    if not admin_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    normalized_value = storage_quota_gb.strip()
    storage_quota_bytes = None
    if normalized_value:
        try:
            storage_quota_bytes = int(float(normalized_value) * 1024 * 1024 * 1024)
        except ValueError:
            return RedirectResponse("/admin?tab=users&error=Invalid quota value", status_code=303)

    try:
        await set_user_storage_quota(admin_user_id, target_user_id, storage_quota_bytes)
        return RedirectResponse("/admin?tab=users", status_code=303)
    except ValueError as error:
        return RedirectResponse(f"/admin?tab=users&error={str(error)}", status_code=303)


@router.post("/admin/disks")
async def updateAdminDisks(request: Request, selected_disks: list[str] = Form(default=[])):
    sid = request.cookies.get("session_id")
    admin_user_id = get_user_id(sid)
    if not admin_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        await update_active_upload_disks(admin_user_id, selected_disks)
        return RedirectResponse("/admin?tab=disk", status_code=303)
    except ValueError as error:
        return RedirectResponse(f"/admin?tab=disk&error={str(error)}", status_code=303)


@router.post("/admin/shares/files/{file_public_id}/revoke")
async def revokeAdminFileShare(request: Request, file_public_id: str):
    sid = request.cookies.get("session_id")
    admin_user_id = get_user_id(sid)
    if not admin_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        await revoke_file_share(admin_user_id, file_public_id)
        return RedirectResponse("/admin?tab=access", status_code=303)
    except ValueError as error:
        return RedirectResponse(f"/admin?tab=access&error={str(error)}", status_code=303)


@router.post("/admin/shares/folders/{folder_public_id}/revoke")
async def revokeAdminFolderShare(request: Request, folder_public_id: str):
    sid = request.cookies.get("session_id")
    admin_user_id = get_user_id(sid)
    if not admin_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        await revoke_folder_share(admin_user_id, folder_public_id)
        return RedirectResponse("/admin?tab=access", status_code=303)
    except ValueError as error:
        return RedirectResponse(f"/admin?tab=access&error={str(error)}", status_code=303)
