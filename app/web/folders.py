import unicodedata
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from app.security.passwords import verify_password
from app.security.sesions import get_user_id
from app.security.share_tokens import create_share_access_token, verify_share_access_token
from app.services.app import UpdateFolderShareSettingsPayload, UpdateFolderVisibilityPayload
from app.services.folders import (
    can_user_access_shared_folder,
    collect_folder_zip_entries,
    create_folder,
    create_folder_zip_file,
    get_folder_share_settings,
    getFoldersContent,
    get_folder_share_access_cookie_name,
    get_move_targets,
    get_public_folder_content,
    get_shared_folder_content,
    get_shared_root_content,
    is_public_folder_accessible,
    set_folder_visibility,
    update_folder_share_settings,
)
from app.db.folders import get_folder_by_public_id
from config import COOKIE_SECURE, TEMPLATES_DIR


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def build_content_disposition(disposition: str, filename: str) -> str:
    fallback_name = unicodedata.normalize("NFKD", filename or "file")
    fallback_name = fallback_name.encode("ascii", "ignore").decode("ascii").strip() or "file"
    fallback_name = fallback_name.replace("\\", "_").replace('"', "_")
    fallback_name = "".join(
        character if 32 <= ord(character) < 127 else "_"
        for character in fallback_name
    )
    encoded_name = quote(filename or "file", safe="")
    return f'{disposition}; filename="{fallback_name}"; filename*=UTF-8\'\'{encoded_name}'


def cleanup_temporary_file(path: str):
    Path(path).unlink(missing_ok=True)


def has_valid_folder_share_cookie(request: Request, folder: dict) -> bool:
    return verify_share_access_token(
        "folder",
        folder["publicID"],
        folder.get("publicPasswordHash"),
        request.cookies.get(get_folder_share_access_cookie_name(folder["publicID"]))
    )


def can_access_folder_share(request: Request, user_id: int | None, folder: dict) -> bool:
    if user_id and folder["userID"] == user_id:
        return True
    if not is_public_folder_accessible(folder):
        return False
    if not folder.get("publicPasswordHash"):
        return True
    return has_valid_folder_share_cookie(request, folder)


@router.post("/app/api/create-folder")
async def createFolder(request: Request):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    data = await request.json()
    folderName = data.get("name")
    url = data.get("URLc")

    if not folderName:
        raise HTTPException(status_code=400, detail="Folder name is required")

    try:
        folder = await create_folder(folderName, user_id, url)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    if folder == 1:
        return {"error": 1}

    return {
        "folder": folder.folder
    }


@router.get("/app/shared")
async def sharedItems(request: Request):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if not user_id:
        return RedirectResponse("/", status_code=303)

    items = await get_shared_root_content(user_id)
    return templates.TemplateResponse(
        "app.html",
        {
            "request": request,
            "folders": items.folders,
            "files": items.files,
            "breadcrumbs": items.breadcrumbs,
            "folder_tree": items.folder_tree,
            "read_only": True,
            "shared_mode": True,
            "search_scope": "local",
            "show_search_filters": False
        }
    )


@router.get("/app/folders/{publicID}")
async def folders(request: Request, publicID: str):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)

    items = None
    read_only = False

    if user_id:
        try:
            items = await getFoldersContent(user_id, publicID)
        except ValueError:
            items = None

        if items == "root":
            return RedirectResponse("/app/home", status_code=303)

        if items is None:
            try:
                items = await get_shared_folder_content(user_id, publicID)
                read_only = True
            except ValueError:
                items = None

    if items is None:
        public_folder = await get_folder_by_public_id(publicID)
        if public_folder and is_public_folder_accessible(public_folder) and not can_access_folder_share(request, user_id, public_folder):
            return templates.TemplateResponse(
                "share_unlock.html",
                {
                    "request": request,
                    "item_type": "folder",
                    "item_name": public_folder["folderName"],
                    "unlock_action": f"/app/folders/{publicID}/unlock",
                    "back_url": "/app/home" if user_id else "/",
                    "error": None
                }
            )

        try:
            items = await get_public_folder_content(publicID)
            read_only = True
        except ValueError:
            return RedirectResponse("/app/home" if user_id else "/", status_code=303)


    return templates.TemplateResponse(
        "app.html",
        {
            "request": request,
            "folders": items.folders,
            "files": items.files,
            "breadcrumbs": items.breadcrumbs,
            "folder_tree": items.folder_tree,
            "read_only": read_only,
            "shared_mode": read_only,
            "search_scope": "local" if read_only else "own",
            "show_search_filters": not read_only
        }
    )


@router.post("/app/folders/{publicID}/unlock")
async def unlockFolder(request: Request, publicID: str, password: str = Form(...)):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    folder = await get_folder_by_public_id(publicID)
    if not folder or not is_public_folder_accessible(folder):
        raise HTTPException(status_code=404, detail="Folder was not found")

    if not folder.get("publicPasswordHash"):
        return RedirectResponse(f"/app/folders/{publicID}", status_code=303)

    if not verify_password(password, folder["publicPasswordHash"]):
        return templates.TemplateResponse(
            "share_unlock.html",
            {
                "request": request,
                "item_type": "folder",
                "item_name": folder["folderName"],
                "unlock_action": f"/app/folders/{publicID}/unlock",
                "back_url": "/app/home" if user_id else "/",
                "error": "Incorrect password"
            },
            status_code=400
        )

    response = RedirectResponse(f"/app/folders/{publicID}", status_code=303)
    response.set_cookie(
        get_folder_share_access_cookie_name(publicID),
        create_share_access_token("folder", publicID, folder.get("publicPasswordHash")),
        max_age=60 * 60 * 12,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE
    )
    return response


@router.get("/app/api/move-targets")
async def getMoveTargets(request: Request):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        return await get_move_targets(user_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/app/api/folders/{folder_public_id}/download")
async def downloadFolder(request: Request, folder_public_id: str):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    folder = await get_folder_by_public_id(folder_public_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder was not found")

    has_private_access = bool(
        user_id
        and (
            folder["userID"] == user_id
            or await can_user_access_shared_folder(user_id, folder)
        )
    )
    if not has_private_access and not can_access_folder_share(request, user_id, folder):
        raise HTTPException(status_code=404, detail="Folder was not found")

    root_name, folder_entries, file_entries = await collect_folder_zip_entries(
        folder,
        include_private=has_private_access
    )
    archive_path = await run_in_threadpool(
        create_folder_zip_file,
        root_name,
        folder_entries,
        file_entries
    )
    archive_name = f"{root_name}.zip"

    return FileResponse(
        path=archive_path,
        media_type="application/zip",
        headers={
            "Content-Disposition": build_content_disposition("attachment", archive_name)
        },
        background=BackgroundTask(cleanup_temporary_file, archive_path)
    )


@router.post("/app/api/folders/{folder_public_id}/visibility")
async def updateFolderVisibility(request: Request, folder_public_id: str):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    data = await request.json()
    payload = UpdateFolderVisibilityPayload(
        folder_public_id=folder_public_id,
        is_public=bool(data.get("public"))
    )

    try:
        return await set_folder_visibility(user_id, payload.folder_public_id, payload.is_public)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/app/api/folders/{folder_public_id}/share-settings")
async def updateFolderShareSettings(request: Request, folder_public_id: str):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    data = await request.json()
    payload = UpdateFolderShareSettingsPayload(
        folder_public_id=folder_public_id,
        is_public=bool(data.get("public")),
        expires_at=data.get("expiresAt"),
        password=data.get("password"),
        clear_password=bool(data.get("clearPassword")),
        shared_users=data.get("sharedUsers") or []
    )

    try:
        return await update_folder_share_settings(
            user_id,
            payload.folder_public_id,
            payload.is_public,
            payload.expires_at,
            payload.password,
            payload.clear_password,
            payload.shared_users
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/app/api/folders/{folder_public_id}/share-settings")
async def getFolderShareSettings(request: Request, folder_public_id: str):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        return await get_folder_share_settings(user_id, folder_public_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
