from fastapi import APIRouter, Request, Form
from app.schemas import schemas
from fastapi.templating import Jinja2Templates


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")



@router.get("/app")
async def main(request: Request):
    return templates.TemplateResponse(
        "app.html",
        {
            "request": request
        }
    )

