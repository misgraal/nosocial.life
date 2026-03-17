from fastapi import FastAPI
from app.web import router
from fastapi.staticfiles import StaticFiles
from app.db.db import lifespan
from config import DISKS


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(router)