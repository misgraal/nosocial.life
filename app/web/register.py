from fastapi import APIRouter, Request, Form
from app.schemas import schemas
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from app.services.register import register


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")



@router.post("/register")
async def main(
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str | None = Form(None),
):
    result = await register(username, password, confirm_password)
    if result.success == True:
        return RedirectResponse("/app", status_code=303)
    else: 
        return RedirectResponse(f"/?error={result.error}", status_code=303)

