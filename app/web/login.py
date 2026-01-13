from fastapi import APIRouter, Request, Form
from app.schemas import schemas
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from app.services.login import login


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
        return RedirectResponse("/app", status_code=303)
    else: 
        error = "Incorect username or password" if result.error == 1 else "User does not exist"
        return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "error": error
        }
    )