from fastapi import APIRouter, Request, Form
from app.schemas import schemas
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from app.services.login import login
from app.security.sesions import create_session
from app.db.login import get_user_id


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")



@router.post("/login")
async def main(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str | None = Form(None),
):
    result = await login(username, password)
    if result.success == True:
        sid = create_session(await get_user_id(username))
        resp = RedirectResponse("/app", status_code=303)
        resp.set_cookie(
            "session_id",
            sid,
            httponly=True,
            samesite="lax",
            secure=False,
            max_age=60*60*24*7
        )
        resp.set_cookie(
            "username",
            username,
            max_age=60*60*24*7,
            httponly=True,
            samesite="lax",
            secure=False,
        )
        return resp
    else: 
        error = "Incorect username or password" if result.error == 1 else "User does not exist"
        return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "error": error
        }
    )