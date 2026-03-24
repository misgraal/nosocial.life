from fastapi import APIRouter, Request, Form
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
    print(folders, files)
    resp = templates.TemplateResponse(
        "app.html",
        {
            "request": request,
            "folders": folders,
            "files": files
        }
    )
    return resp

@router.get("/app/create-folder")
async def createFolder(request: Request):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if not user_id:
        return RedirectResponse("/", status_code=303)

    data = await request.json()
    folderName = data.get("name")

    create_folder(folderName, user_id)

@router.get("/app/folders")
async def folders(request: Request):
    pass

