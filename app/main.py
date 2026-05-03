from fastapi import FastAPI
from fastapi import Request
from app.web import router
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from app.db.db import lifespan
from config import STATIC_DIR
from starlette.middleware.gzip import GZipMiddleware
from urllib.parse import urlparse


class CachedStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers.setdefault("Cache-Control", "public, max-age=604800")
        return response


app = FastAPI(lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.mount("/static", CachedStaticFiles(directory=str(STATIC_DIR)), name="static")


@app.middleware("http")
async def reject_cross_site_writes(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        host = request.headers.get("host", "")
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        source = origin or referer

        if source:
            source_host = urlparse(source).netloc
            if source_host and source_host != host:
                return JSONResponse({"detail": "Cross-site request blocked"}, status_code=403)

    return await call_next(request)


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    return FileResponse(
        str(STATIC_DIR / "sw.js"),
        media_type="application/javascript",
        headers={
            "Service-Worker-Allowed": "/",
            "Cache-Control": "no-cache"
        }
    )


app.include_router(router)
