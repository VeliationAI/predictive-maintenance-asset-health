from fastapi import APIRouter

from . import assets, audit, auth, ops

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(assets.router, prefix="/assets", tags=["assets"])
api_router.include_router(ops.router, prefix="/ops", tags=["ops"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
