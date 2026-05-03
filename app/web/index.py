from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from app.security.sesions import get_user_id
from config import TEMPLATES_DIR


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))



@router.get("/")
async def main(request: Request):
    sid = request.cookies.get("session_id")
    if get_user_id(sid):
        return RedirectResponse("/app/home", status_code=303)

    errorCode = request.query_params.get("error")
    error = ""
    match errorCode:
        case "1":
            error = "Password do not match."
        case "2":
            error = "User already exists."
        case _:
            error = ""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "error": error,
            "auth_mode": request.query_params.get("mode") or "login"
        }
    )
