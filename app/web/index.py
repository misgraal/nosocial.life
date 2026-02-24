from fastapi import APIRouter, Request, Form
from app.schemas import schemas
from fastapi.templating import Jinja2Templates
from app.security.sesions import get_user_id
from fastapi.responses import RedirectResponse



router = APIRouter()
templates = Jinja2Templates(directory="app/templates")



@router.get("/")
async def main(request: Request):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if user_id:
        return RedirectResponse("/app", status_code=303)

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
            "error": error
        }
    )

