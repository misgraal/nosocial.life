from fastapi import APIRouter, Request, Form
from app.schemas import schemas
from fastapi.templating import Jinja2Templates
from app.security.sesions import get_user_id
from fastapi.responses import RedirectResponse
from app.db.app import get_user_username_by_id


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")



@router.get("/app")
async def main(request: Request):
    
    
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if not user_id:
        return RedirectResponse("/", status_code=303)
    resp = templates.TemplateResponse(
        "app.html",
        {
            "request": request
        }
    )
    return resp

