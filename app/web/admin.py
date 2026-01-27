from fastapi import APIRouter, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from app.security.sesions import get_user_id
from app.services.admin import *


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")



@router.get("/admin")
async def main(request: Request):
    
    
    sid = request.cookies.get("session_id")
    user_id = get_user_id(sid)
    if not user_id:
        return RedirectResponse("/", status_code=303)
    result = await admin(user_id)
    if result.success == True:
        usersResponce = await get_info()
        users = usersResponce.users
        resp = templates.TemplateResponse(
            "admin.html",
            {
                "request": request,
                "users": users
            }
        )
    else:
        return RedirectResponse("/app", status_code=303)
        
    return resp

