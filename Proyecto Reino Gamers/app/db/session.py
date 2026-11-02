# Motor de conexión a PostgreSQL
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# pool_pre_ping evita conexiones muertas; pool_recycle para conexiones largas
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    """Sesión por request (usada como dependencia de FastAPI)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
