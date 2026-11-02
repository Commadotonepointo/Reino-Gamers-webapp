# ------------------------------------------------------------
# Semillas iniciales:
#   - Usuario administrador
#   - Catálogo de productos (gaming + cloud) con variantes
# Ejecución:  python scripts/seed.py
# ------------------------------------------------------------
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings                                   # noqa: E402
from app.core.security import hash_password                           # noqa: E402
from app.db.session import SessionLocal, engine                       # noqa: E402
from app.models import Base                                           # noqa: E402
from app.models.product import Product, ProductVariant                # noqa: E402
from app.models.user import User                                      # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("seed")

# (slug, nombre, categoría, plataforma, [denominaciones USD])
CATALOG = [
    # ---- GIFT CARDS DE VIDEOJUEGOS ----
    ("steam",               "Steam Gift Card",                "gaming", "steam",        [5, 10, 20, 50, 100]),
    ("playstation",         "PlayStation Store Gift Card",    "gaming", "playstation",  [10, 25, 50, 100]),
    ("xbox",                "Xbox / Microsoft Gift Card",     "gaming", "xbox",         [10, 25, 50, 100]),
    ("nintendo",            "Nintendo eShop Gift Card",       "gaming", "nintendo",     [10, 20, 35, 50]),
    ("google-play",         "Google Play Gift Card",          "gaming", "google_play",  [10, 25, 50, 100]),
    ("apple-itunes",        "Apple / iTunes Gift Card",       "gaming", "apple",        [5, 10, 25, 50, 100]),
    ("roblox",              "Roblox Robux Gift Card",         "gaming", "roblox",       [10, 25, 50]),
    ("free-fire",           "Free Fire Diamonds",             "gaming", "free_fire",    [10, 25, 50]),
    ("riot-points",         "Riot VALORANT / LoL Points",     "gaming", "riot",         [10, 25, 50]),
    ("razer-gold",          "Razer Gold Gift Card",           "gaming", "razer_gold",   [5, 10, 25, 50]),
    # ---- ALMACENAMIENTO EN LA NUBE ----
    ("google-one",          "Google One (almacenamiento)",    "cloud_storage", "google_one", [100, 200]),
    ("onedrive",            "Microsoft OneDrive",             "cloud_storage", "onedrive",   [50, 100]),
    ("dropbox",             "Dropbox Plus",                   "cloud_storage", "dropbox",    [100, 200]),
    ("pcloud",              "pCloud Premium",                 "cloud_storage", "pcloud",     [100, 200, 500]),
]

MARGIN_NOTE = "Precios de venta USD; el costo real depende del proveedor central."


def seed_admin(db) -> None:
    email = os.getenv("ADMIN_EMAIL")
    password = os.getenv("ADMIN_PASSWORD")
    if not email or not password:
        log.info("Prueba: ADMIN_EMAIL/ADMIN_PASSWORD no definidos en .env. Se omite el admin.")
        return
    from sqlalchemy import select
    exists = db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()
    if exists:
        log.info("Admin %s ya existía.", email)
        return
    db.add(User(email=email.lower(), password_hash=hash_password(password),
                full_name="Administrador", role="admin"))
    db.commit()
    log.info("✅ Admin creado: %s", email)


def seed_catalog(db) -> None:
    from sqlalchemy import select
    created_products = 0
    created_variants = 0
    for slug, name, category, platform, denominations in CATALOG:
        product = db.execute(select(Product).where(Product.slug == slug)).scalar_one_or_none()
        if not product:
            product = Product(
                slug=slug,
                name=name,
                category=category,
                platform=platform,
                description=f"Tarjeta de regalo digital oficial de {name}. "
                            f"Entrega inmediata del código por correo.",
            )
            db.add(product)
            db.flush()
            created_products += 1

        for denom in denominations:
            sku = f"SC-{platform.upper()}-USD{denom:g}-GLOBAL"
            if db.execute(select(ProductVariant).where(ProductVariant.sku == sku)).scalar_one_or_none():
                continue
            db.add(ProductVariant(
                product_id=product.id,
                sku=sku,
                denomination=denom,
                currency="USD",
                region="GLOBAL",
                price_usd=round(denom * 1.08, 2),   # margen de ejemplo a ajustar
            ))
            created_variants += 1
    db.commit()
    log.info("✅ Productos creados: %d. Variantes creadas: %d.", created_products, created_variants)


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_admin(db)
        seed_catalog(db)
        log.info("Semillas completadas. Próximo paso: cargar códigos de gift cards "
                 "con POST /api/v1/admin/codes.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
