from fastapi import APIRouter, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from app.db.app import create_audit_log
from app.services.register import register
from app.security.sesions import create_session
from app.security.rate_limit import check_rate_limit, clear_rate_limit
from config import COOKIE_SECURE, TEMPLATES_DIR


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))



@router.post("/register")
async def main(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str | None = Form(None),
):
    rate_limit_key = f"register:{request.client.host if request.client else 'unknown'}"
    try:
        check_rate_limit(rate_limit_key)
    except ValueError as error:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": str(error),
                "auth_mode": "register"
            },
            status_code=429
        )

    result = await register(username, password, confirm_password)
    if result.success == True:
        clear_rate_limit(rate_limit_key)
        sid = create_session(
            result.user_id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent")
        )
        await create_audit_log(
            result.user_id,
            "auth.register",
            "user",
            str(result.user_id),
            {"username": result.username}
        )
        resp = RedirectResponse("/app/home", status_code=303)
        resp.set_cookie(
            "session_id",
            sid,
            httponly=True,
            samesite="lax",
            secure=COOKIE_SECURE,
            max_age=60*60*24*7
        )
        resp.set_cookie(
            "username",
            result.username,
            max_age=60*60*24*7,
            httponly=True,
            samesite="lax",
            secure=COOKIE_SECURE,
        )
        return resp
    else: 
        error = (
            "Passwords do not match" if result.error == 1
            else "User already exists" if result.error == 2
            else "Username must be 3-64 characters and use only letters, numbers, dots, underscores, dashes or @"
            if result.error == 3
            else "Password is required"
        )
        return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "error": error,
            "auth_mode": "register"
        }
    )
