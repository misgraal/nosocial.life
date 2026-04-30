from fastapi import APIRouter, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from app.db.app import create_audit_log
from app.services.login import login
from app.security.sesions import create_session


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
        sid = create_session(result.user_id)
        await create_audit_log(result.user_id, "auth.login", "user", str(result.user_id), {"username": username})
        resp = RedirectResponse("/app/home", status_code=303)
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
        error = (
            "Incorrect username or password" if result.error == 1
            else "User does not exist" if result.error == 2
            else "User is blocked"
        )
        return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "error": error
        }
    )
