import mimetypes
import unicodedata
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db.files import get_file_by_public_id
from app.security.sesions import get_user_id
from app.security.passwords import verify_password
from app.services.app import UpdateFileShareSettingsPayload, UpdateFileVisibilityPayload, UploadChunkPayload
from app.services.files import (
    get_file_share_settings,
    get_share_access_cookie_name,
    get_accessible_file,
    get_excel_file_preview,
    get_file_view_kind,
    get_file_view_type_label,
    handle_chunk_upload,
    is_public_file_accessible,
    is_share_password_required,
    read_text_file_preview,
    set_file_visibility,
    update_file_share_settings,
)
from config import TEMPLATES_DIR


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


def has_valid_file_share_cookie(request: Request, file: dict) -> bool:
    return request.cookies.get(get_share_access_cookie_name(file["publicID"])) == "1"


def can_access_file_share(request: Request, user_id: int | None, file: dict) -> bool:
    if user_id and file["userID"] == user_id:
        return True
    if not is_public_file_accessible(file):
        return False
    if not is_share_password_required(file):
        return True
    return has_valid_file_share_cookie(request, file)


@router.get("/app/files/{publicID}")
async def openFile(request: Request, publicID: str):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    file = await get_accessible_file(user_id, publicID) if user_id else await get_accessible_file(None, publicID)
    if not file:
        if not user_id:
            return RedirectResponse("/", status_code=303)
        raise HTTPException(status_code=404, detail="File was not found")

    if not can_access_file_share(request, user_id, file):
        return templates.TemplateResponse(
            "share_unlock.html",
            {
                "request": request,
                "item_type": "file",
                "item_name": file["fileName"],
                "unlock_action": f"/app/files/{publicID}/unlock",
                "back_url": "/app/home" if user_id else "/",
                "error": None
            }
        )

    file_path = Path(file["serverPath"])
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File is missing on disk")

    view_kind = get_file_view_kind(file["fileName"])
    text_preview = None
    excel_preview = None

    if view_kind == "text":
        try:
            text_preview = read_text_file_preview(file_path)
        except Exception:
            view_kind = "unsupported"

    if view_kind == "excel":
        try:
            excel_preview = get_excel_file_preview(file_path)
        except Exception:
            excel_preview = {"supported": False}
        if not excel_preview.get("supported"):
            view_kind = "unsupported"

    return templates.TemplateResponse(
        "file_viewer.html",
        {
            "request": request,
            "file": file,
            "view_kind": view_kind,
            "file_type_label": get_file_view_type_label(file["fileName"]),
            "raw_file_url": f"/app/api/files/{publicID}/content",
            "download_url": f"/app/api/files/{publicID}/download",
            "text_preview": text_preview,
            "excel_preview": excel_preview
        }
    )


@router.post("/app/files/{publicID}/unlock")
async def unlockFile(request: Request, publicID: str, password: str = Form(...)):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    file = await get_file_by_public_id(publicID)
    if not file or not is_public_file_accessible(file):
        raise HTTPException(status_code=404, detail="File was not found")

    if not is_share_password_required(file):
        return RedirectResponse(f"/app/files/{publicID}", status_code=303)

    if not verify_password(password, file["publicPasswordHash"]):
        return templates.TemplateResponse(
            "share_unlock.html",
            {
                "request": request,
                "item_type": "file",
                "item_name": file["fileName"],
                "unlock_action": f"/app/files/{publicID}/unlock",
                "back_url": "/app/home" if user_id else "/",
                "error": "Incorrect password"
            },
            status_code=400
        )

    response = RedirectResponse(f"/app/files/{publicID}", status_code=303)
    response.set_cookie(get_share_access_cookie_name(publicID), "1", max_age=60 * 60 * 12, httponly=True, samesite="lax")
    return response


@router.get("/app/api/files/{file_public_id}/content")
async def getFileContent(request: Request, file_public_id: str):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    private_access_file = await get_accessible_file(user_id, file_public_id) if user_id else None
    file = private_access_file
    if not file:
        file = await get_file_by_public_id(file_public_id)
    if not file or not (private_access_file or can_access_file_share(request, user_id, file)):
        raise HTTPException(status_code=404, detail="File was not found")

    file_path = Path(file["serverPath"])
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File is missing on disk")

    media_type, _ = mimetypes.guess_type(file["fileName"])
    return FileResponse(
        path=str(file_path),
        media_type=media_type or "application/octet-stream",
        headers={
            "Content-Disposition": build_content_disposition("inline", file["fileName"])
        }
    )


@router.get("/app/api/files/{file_public_id}/preview")
async def getFilePreview(request: Request, file_public_id: str):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    private_access_file = await get_accessible_file(user_id, file_public_id) if user_id else None
    file = private_access_file
    if not file:
        file = await get_file_by_public_id(file_public_id)
    if not file or not (private_access_file or can_access_file_share(request, user_id, file)):
        raise HTTPException(status_code=404, detail="File was not found")

    file_path = Path(file["serverPath"])
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File is missing on disk")

    view_kind = get_file_view_kind(file["fileName"])
    response = {
        "viewKind": view_kind,
        "fileTypeLabel": get_file_view_type_label(file["fileName"]),
        "rawFileUrl": f"/app/api/files/{file_public_id}/content"
    }

    if view_kind == "text":
        try:
            response["textPreview"] = read_text_file_preview(file_path)
        except Exception:
            response["viewKind"] = "unsupported"
        return response

    if view_kind == "excel":
        try:
            excel_preview = get_excel_file_preview(file_path)
        except Exception:
            excel_preview = {"supported": False}

        if not excel_preview.get("supported"):
            response["viewKind"] = "unsupported"
        else:
            response["excelPreview"] = excel_preview
        return response

    return response


@router.post("/app/api/upload")
async def fileUpload(
    request: Request,
    chunk: UploadFile = File(...),
    uploadId: str = Form(...),
    fileName: str = Form(...),
    mimeType: str = Form(...),
    fileSize: int = Form(...),
    chunkIndex: int = Form(...),
    totalChunks: int = Form(...),
    chunkSize: int = Form(...),
    isLastChunk: str = Form(...),
    currentUrl: str = Form(...),
    folderPublicId: str | None = Form(default=None),
    relativePath: str | None = Form(default=None)
):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    chunk_bytes = await chunk.read()
    payload = UploadChunkPayload(
        upload_id=uploadId,
        file_name=fileName,
        mime_type=mimeType,
        file_size=fileSize,
        chunk_index=chunkIndex,
        total_chunks=totalChunks,
        chunk_size=chunkSize,
        is_last_chunk=str(isLastChunk).lower() == "true",
        current_url=currentUrl,
        folder_public_id=folderPublicId,
        relative_path=relativePath
    )

    try:
        return await handle_chunk_upload(user_id, payload, chunk_bytes)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/app/api/files/{file_public_id}/download")
async def downloadFile(request: Request, file_public_id: str):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    private_access_file = await get_accessible_file(user_id, file_public_id) if user_id else None
    file = private_access_file
    if not file:
        file = await get_file_by_public_id(file_public_id)
    has_private_access = bool(private_access_file)
    if not file or not (has_private_access or can_access_file_share(request, user_id, file)):
        raise HTTPException(status_code=404, detail="File was not found")
    if not has_private_access and file["userID"] != user_id and not file.get("publicAllowDownload", True):
        raise HTTPException(status_code=403, detail="Public download is disabled for this file")

    file_path = Path(file["serverPath"])
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File is missing on disk")

    return FileResponse(
        path=str(file_path),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": build_content_disposition("attachment", file["fileName"])
        }
    )


@router.post("/app/api/files/{file_public_id}/visibility")
async def updateFileVisibility(request: Request, file_public_id: str):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    data = await request.json()
    payload = UpdateFileVisibilityPayload(
        file_public_id=file_public_id,
        is_public=bool(data.get("public"))
    )

    try:
        return await set_file_visibility(user_id, payload.file_public_id, payload.is_public)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/app/api/files/{file_public_id}/share-settings")
async def updateFileShareSettings(request: Request, file_public_id: str):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    data = await request.json()
    payload = UpdateFileShareSettingsPayload(
        file_public_id=file_public_id,
        is_public=bool(data.get("public")),
        expires_at=data.get("expiresAt"),
        password=data.get("password"),
        clear_password=bool(data.get("clearPassword")),
        allow_download=bool(data.get("allowDownload", True)),
        shared_users=data.get("sharedUsers") or []
    )

    try:
        return await update_file_share_settings(
            user_id,
            payload.file_public_id,
            payload.is_public,
            payload.expires_at,
            payload.password,
            payload.clear_password,
            payload.allow_download,
            payload.shared_users
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/app/api/files/{file_public_id}/share-settings")
async def getFileShareSettings(request: Request, file_public_id: str):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        return await get_file_share_settings(user_id, file_public_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
