# 🎮 Reino Gamers — Backend E-commerce

Backend de tienda en línea para la venta de **tarjetas de regalo / gift cards** de plataformas de
videojuegos (Steam, PlayStation, Xbox, Nintendo, Google Play, Apple, Roblox, Free Fire, Razer Gold, etc.)
y de **almacenantamiento en la nube** (Google One, OneDrive, Dropbox, pCloud, MEGA, iCloud…).

**Método principal de pago: Binance Pay (USDT).**

---

## 🧱 Stack

| Componente | Tecnología |
|---|---|
| Lenguaje | Python 3.11+ |
| Framework web | FastAPI |
| Base de datos | PostgreSQL 14+ |
| ORM | SQLAlchemy 2.0 (modo síncrono) |
| Validación | Pydantic v2 + pydantic-settings |
| Auth | JWT (python-jose) + bcrypt (passlib) |
| Cifrado de códigos | Fernet (sqlite no; derivado de la `APP_SECRET_KEY`) |
| HTTP | httpx (para llamar a la API de Binance Pay) |
| Correos | smtplib (SMTP) — entrega de códigos |

---

## 📁 Estructura del proyecto

```
Proyecto Reino Gamers/
├── README.md
├── docs/
│   └── ESQUEMA_PROYECTO.md      ← Plan maestro y fases del proyecto
├── .env.example                 ← COPIAR a .env y colocar credenciales
├── requirements.txt
├── database/
│   └── schema.sql               ← DDL completo de PostgreSQL (referencia / manual)
├── app/
│   ├── main.py                  ← App FastAPI + arranque
│   ├── core/
│   │   ├── config.py            ← Lectura de .env (credenciales van aquí)
│   │   ├── security.py          ← JWT, hash de contraseñas, roles
│   │   └── crypto.py            ← Cifrado de códigos de gift card
│   ├── db/
│   │   ├── session.py           ← Motor SQLAlchemy + SessionLocal
│   │   └── base.py              ← Base declarativa (crea tablas al arrancar)
│   ├── models/                  ← Modelas SQLAlchemy (tablas)
│   │   ├── user.py  product.py  order.py  payment.py  setting.py
│   ├── schemas/                 ← Modelos Pydantic (API)
│   ├── api/
│   │   ├── deps.py              ← Dependencias (get_db, get_current_user/admin)
│   │   └── v1/
│   │       ├── router.py        ← Agrega todos los routers
│   │       └── endpoints/
│   │           ├── auth.py      ← Registro / login / "quién soy"
│   │           ├── catalog.py   ← Catálogo público (productos + variantes)
│   │           ├── orders.py    ← Crear pedido / listar / consultar
│   │           ├── payments.py  ← Binance Pay: crear orden, webhook, verificar
│   │           └── admin.py     ← Gestión de productos, inventario de códigos, pedidos
│   └── services/
│       ├── binance_pay.py       ← Cliente Binance Pay (firma HMAC-SHA512 + USDT)
│       ├── inventory.py         ← Reserva/entrega atómica de códigos
│       └── delivery.py          ← Entrega de códigos por correo
└── scripts/
    └── seed.py                  ← Semillas: admin + catálogo inicial
```

---

## ⚙️ Puesta en marcha

```bash
# 1. Entorno virtual + dependencias
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# 2. Variables: copiar y completar credenciales
copy .env.example .env          # colocar credenciales de Binance Pay, BD, SMTP…

# 3. Crear la base de datos (opcional, la app también la crea automática con create_all)
psql -U postgres -c "CREATE DATABASE reino_gamers;"

# 4. Sembrar datos iniciales (admin + catálogo)
python scripts/seed.py

# 5. Levantar el servidor
uvicorn app.main:app --reload
```

- Documentación interactiva: `http://localhost:8000/docs`
- Docs alternativas (ReDoc): `http://localhost:8000/redoc`

---

## 🔑 Dónde colocar cada credencial

Todas las credenciales se colocan en el archivo **`.env`** (ver `.env.example`)
y las lee `app/core/config.py` con pydantic-settings. Nunca se suben a Git (está en `.gitignore`).

| Credencial | Variable de entorno | Dónde obtenerla |
|---|---|---|
| Base de datos | `DATABASE_URL` | Tu servidor PostgreSQL (usuario/contraseña/host/puerto/nombre) |
| Binance Pay API Key | `BINANCE_PAY_API_KEY` | Binance Merchant Portal → Merchant Pay Settings → **API Key** |
| Binance Pay API Secret | `BINANCE_PAY_API_SECRET` | Binance Merchant Portal → Merchant Pay Settings → **API Secret** |
| URL de API | `BINANCE_PAY_BASE_URL` | Producción `https://api.binance.com` · SandBox `https://bpay.binanceapi.com` |
| Secreta de la app / JWT | `APP_SECRET_KEY` | Generar con: `python -c "import secrets; print(secrets.token_hex(32))"` |
| Clave de cifrado de códigos | `CODE_ENCRYPTION_KEY` | Generar con Fernet (ver `.env.example`) |
| Correo (entrega de códigos) | `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` | Tu proveedor de correo |
| Dominio público | `PUBLIC_BASE_URL` | El dominio donde servirá la web (para URLs de retorno) |

> ⚠️ La aplicación funciona aunque falten las credenciales de Binance Pay: el NODO de pago
> se crea y devuelve un error descriptivo. En cuanto coloques las credenciales en `.env`,
> la integración queda activa sin tocar código.

---

## 🛒 Flujo de compra (resumen)

1. El cliente se registra/inicia sesión (JWT).
2. Explora el catálogo: producto (plataforma) → variante (monto, región) → precio en USD.
3. `POST /api/v1/orders` → se crea el pedido y se **reservan** los códigos en inventario (15 min de reserva).
4. `POST /api/v1/payments/order/{order_id}` → el backend llama a Binance Pay
   (`/binancepay/openapi/v2/order`, moneda **USDT**) y devuelve la `checkoutUrl` para el cliente.
5. El cliente paga con USDT en Binance.
6. Binance Pay envía el **webhook** a `POST /api/v1/payments/webhook/binance` →
   se marca el pago confirmado, se asigna definitivamente el código y se entrega por correo, o se consulta
   manualmente con `POST /api/v1/payments/{payment_id}/check` (verificación de estado contra Binance).
7. El pedido queda `delivered` y el cliente ve sus códigos en su cuenta (`GET /api/v1/orders/{id}`).

---

## 🗃️ Modelo de datos (esquema)

```
users            clientes y administradores (rol, hash bcrypt)
products         catálogo: Steam, PlayStation, Google One, Dropbox… (categoría gaming|cloud_storage)
product_variants denominaciones: $10 Global, $50 AR… por producto (SKU, precio USD)
gift_card_codes  inventario de códigos CIFRADOS por variante (available|reserved|sold|void)
orders           pedidos (pending → paid/delivered/cancelled/expired)
order_items      ítems del pedido (variante, cantidad, precios)
payments         pasarela por pago (binance_pay|otras, prepay_id, checkout_url, montos, respuestas)
webhook_events   bitácora cruda de TODOS los webhooks recibidos (auditoría)
settings         configuración editable del sitio (clave/valor, para admin)
```

Diagrama detallado y reglas de negocio: `docs/ESQUEMA_PROYECTO.md` ·
DDL SQL completo: `database/schema.sql`.

---

## 🗺️ Ruta al MVP (ver fases completas en docs)

- **Fase 1 (✅ hecho aquí):** backend completo, BD, autenticación, catálogo, pedidos, inventario
  cifrado de códigos, integración Binance Pay USDT preparada para credenciales, webhooks, entrega por correo, admin.
- **Fase 2:** panel web (frontend) conectado a esta API.
- **Fase 3:** pasarelas adicionales (extensibles via tabla `payments.provider`), cupones, afiliados.
- **Fase 4:** hardening (certificados RSA de webhook completo, monitoreo, backups, CI/CD).
