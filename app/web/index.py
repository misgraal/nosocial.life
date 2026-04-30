from fastapi import APIRouter, Request, Form
from app.schemas import schemas
from fastapi.templating import Jinja2Templates
from config import TEMPLATES_DIR


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))



@router.get("/")
async def main(request: Request):
    errorCode = request.query_params.get("error")
    error = ""
    match errorCode:
        case "1":
            error = "Password do not match."
        case "2":
            error = "User already exists."
        case _:
            error = ""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "error": error
        }
    )
