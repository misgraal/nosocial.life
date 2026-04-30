from fastapi import FastAPI
from app.web import router
from fastapi.staticfiles import StaticFiles
from app.db.db import lifespan
from config import STATIC_DIR


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(router)
