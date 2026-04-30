from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from app.db.app import create_audit_log
from app.security.sesions import delete_session
from app.security.sesions import get_user_id


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")



@router.get("/logout")
async def main(
    request: Request
):
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if user_id:
        await create_audit_log(user_id, "auth.logout", "user", str(user_id), {})
    delete_session(sid)
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("session_id")
    resp.delete_cookie("username")
    return resp
