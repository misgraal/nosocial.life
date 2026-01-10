from fastapi import APIRouter, Request, Form
from app.schemas import schemas
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse



router = APIRouter()
templates = Jinja2Templates(directory="app/templates")



@router.post("/login")
async def main(
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str | None = Form(None),
):
    if password == "123":
        return RedirectResponse("/app", status_code=303)
    else: return RedirectResponse("/", status_code=303)