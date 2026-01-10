from fastapi import APIRouter, Request, Form
from app.schemas import schemas
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")



@router.post("/register")
async def main(request: Request):
    return RedirectResponse("/app", status_code=303)

