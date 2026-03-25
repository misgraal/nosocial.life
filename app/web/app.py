from fastapi import APIRouter, Request, HTTPException
from app.schemas import schemas
from fastapi.templating import Jinja2Templates
from app.security.sesions import get_user_id
from fastapi.responses import RedirectResponse
from app.db.app import get_user_username_by_id
from app.services.app import *


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")



@router.get("/app/home")
async def main(request: Request):
    
    
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if not user_id:
        return RedirectResponse("/", status_code=303)
    items = await home(user_id)
    folders = items.folders
    files = items.files
    resp = templates.TemplateResponse(
        "app.html",
        {
            "request": request,
            "folders": folders,
            "files": files
        }
    )
    return resp

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
    

    folder = await create_folder(folderName, user_id, url)
    if folder == 1:
        return { "error": 1 }

    return {
        "folder": folder.folder
    }

@router.get("/app/folders/{publicID}")
async def folders(request: Request, publicID: str):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if not user_id:
        return RedirectResponse("/", status_code=303)

    items = await getFoldersContent(publicID)
    if items == "root":
        return RedirectResponse("/app/home", status_code=303)


    folders = items.folders
    files = []

    resp = templates.TemplateResponse(
        "app.html",
        {
            "request": request,
            "folders": folders,
            "files": files
        }
    )
    return resp    

