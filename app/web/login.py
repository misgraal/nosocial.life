from fastapi import APIRouter, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from app.db.app import create_audit_log
from app.services.login import login
from app.services.register import normalize_username
from app.security.sesions import create_session
from app.security.rate_limit import check_rate_limit, clear_rate_limit
from config import COOKIE_SECURE, TEMPLATES_DIR


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/login")
async def login_page():
    return RedirectResponse("/", status_code=303)


@router.post("/login")
async def main(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str | None = Form(None),
):
    normalized_username = normalize_username(username)
    rate_limit_key = f"login:{request.client.host if request.client else 'unknown'}:{normalized_username.casefold()}"
    try:
        check_rate_limit(rate_limit_key)
    except ValueError as error:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": str(error),
                "auth_mode": "login"
            },
            status_code=429
        )

    result = await login(username, password)
    if result.success == True:
        clear_rate_limit(rate_limit_key)
        sid = create_session(
            result.user_id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent")
        )
        await create_audit_log(result.user_id, "auth.login", "user", str(result.user_id), {"username": result.username})
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
            "Incorrect username or password" if result.error in {1, 2}
            else "User is blocked"
        )
        return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "error": error,
            "auth_mode": "login"
        }
    )
