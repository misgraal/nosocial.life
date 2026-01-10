from fastapi import APIRouter
from .index import router as index_router
from .app import router as app_router
from .register import router as register_router
from .login import router as login_router

router = APIRouter()

router.include_router(index_router)
router.include_router(app_router)
router.include_router(register_router)
router.include_router(login_router)


