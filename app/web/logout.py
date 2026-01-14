from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from app.security.sesions import delete_session


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")



@router.get("/logout")
async def main(
    request: Request
):
    sid = request.cookies.get("session_id")
    delete_session(sid)
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("session_id")
    resp.delete_cookie("username")
    return resp