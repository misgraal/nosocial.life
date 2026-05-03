from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db.app import create_audit_log
from app.security.sesions import delete_other_user_sessions, get_user_id, list_user_sessions
from config import TEMPLATES_DIR


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def format_session_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


@router.get("/app/sessions")
async def sessionsPage(request: Request):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if not user_id:
        return RedirectResponse("/", status_code=303)

    sessions = [
        {
            **session,
            "createdAtLabel": format_session_time(session["createdAt"]),
            "lastSeenAtLabel": format_session_time(session["lastSeenAt"]),
        }
        for session in list_user_sessions(user_id, sid)
    ]
    return templates.TemplateResponse(
        "sessions.html",
        {
            "request": request,
            "sessions": sessions,
        }
    )


@router.post("/app/sessions/logout-others")
async def logoutOtherSessions(request: Request):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if not user_id:
        return RedirectResponse("/", status_code=303)

    delete_other_user_sessions(user_id, sid)
    await create_audit_log(user_id, "auth.sessions.revoked", "user", str(user_id), {})
    return RedirectResponse("/app/sessions", status_code=303)
