from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates
from app.security.sesions import get_user_id
from fastapi.responses import RedirectResponse

from app.services.app import DeleteItemsPayload, MoveItemsPayload, RenameItemPayload, move_items, rename_item, search_drive
from app.services.files import delete_items
from app.services.folders import home
from config import TEMPLATES_DIR


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))



@router.get("/app/home")
async def main(request: Request):
    
    
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if not user_id:
        return RedirectResponse("/", status_code=303)
    items = await home(user_id)
    folders = items.folders
    files = items.files
    breadcrumbs = items.breadcrumbs
    folder_tree = items.folder_tree
    resp = templates.TemplateResponse(
        "app.html",
        {
            "request": request,
            "folders": folders,
            "files": files,
            "breadcrumbs": breadcrumbs,
            "folder_tree": folder_tree,
            "read_only": False
        }
    )
    return resp

@router.post("/app/api/delete-items")
async def deleteItems(request: Request):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    data = await request.json()
    payload = DeleteItemsPayload(
        folder_public_ids=data.get("folderPublicIds", []),
        file_public_ids=data.get("filePublicIds", [])
    )

    try:
        return await delete_items(user_id, payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/app/api/rename-item")
async def renameItem(request: Request):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    data = await request.json()
    payload = RenameItemPayload(
        folder_public_id=data.get("folderPublicId"),
        file_public_id=data.get("filePublicId"),
        new_name=data.get("newName", "")
    )

    try:
        return await rename_item(user_id, payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
@router.post("/app/api/move-items")
async def moveItems(request: Request):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    data = await request.json()
    payload = MoveItemsPayload(
        folder_public_ids=data.get("folderPublicIds", []),
        file_public_ids=data.get("filePublicIds", []),
        destination_public_id=data.get("destinationPublicId")
    )

    try:
        return await move_items(user_id, payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/app/api/search")
async def searchDrive(
    request: Request,
    query: str = "",
    kind: str = "all",
    min_size: int | None = None,
    max_size: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None
):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        return await search_drive(
            user_id,
            query,
            kind=kind,
            min_size=min_size,
            max_size=max_size,
            date_from=date_from,
            date_to=date_to
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
