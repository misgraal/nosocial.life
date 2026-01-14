from fastapi import APIRouter, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from app.services.register import register


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")



@router.post("/register")
async def main(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str | None = Form(None),
):
    result = await register(username, password, confirm_password)
    if result.success == True:
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

