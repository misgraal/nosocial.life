from fastapi import APIRouter, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from app.db.app import create_audit_log
from app.db.login import get_user_id
from app.services.register import register
from config import TEMPLATES_DIR


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))



@router.post("/register")
async def main(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str | None = Form(None),
):
    result = await register(username, password, confirm_password)
    if result.success == True:
        user_id = await get_user_id(username)
        await create_audit_log(user_id, "auth.register", "user", str(user_id), {"username": username})
        return RedirectResponse("/login")
    else: 
        error = "Passwords do not match" if result.error == 1 else "User already exists"
        return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "error": error
        }
    )
