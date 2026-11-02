# Router v1 — agrupa todos los módulos
from fastapi import APIRouter

from app.api.v1.endpoints import admin, auth, catalog, orders, payments

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(catalog.router)
api_router.include_router(orders.router)
api_router.include_router(payments.router)
api_router.include_router(admin.router)
