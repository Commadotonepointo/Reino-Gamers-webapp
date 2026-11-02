# Main de la app FastAPI — Reino Gamers
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.session import engine
from app.models import Base            # registra todas las tablas
from app.api.v1.router import api_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    description=(
        "Backend de e-commerce de gift cards (videojuegos y almacenamiento en nube). "
        "Método principal de pago: **Binance Pay — USDT**."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS abierto para el frontend (ajustar dominios en producción)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    logger.info("Base de datos inicializada (create_all).")
    if not settings.binance_credentials_ready:
        logger.warning(
            "⚠ Binance Pay sin credenciales: coloca BINANCE_PAY_API_KEY y "
            "BINANCE_PAY_API_SECRET en .env para activar los cobros en USDT."
        )
    if not settings.smtp_ready:
        logger.warning("⚠ SMTP sin configurar: los códigos se imprimirán en el log.")


app.include_router(api_router, prefix="/api/v1")


@app.get("/", tags=["health"])
def root():
    return {
        "service": settings.app_name,
        "status": "ok",
        "docs": "/docs",
        "payment_provider": "binance_pay (USDT)",
        "binance_ready": settings.binance_credentials_ready,
    }


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
