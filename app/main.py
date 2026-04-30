from fastapi import FastAPI
from app.web import router
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.db.db import lifespan
from config import STATIC_DIR


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    return FileResponse(
        str(STATIC_DIR / "sw.js"),
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"}
    )


app.include_router(router)
