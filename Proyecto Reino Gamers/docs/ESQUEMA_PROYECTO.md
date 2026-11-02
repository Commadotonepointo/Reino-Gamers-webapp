# 📋 ESQUEMA MAESTRO — Proyecto Reino Gamers

Documento de planificación: cómo se debe realizar el proyecto, fases, flujos, modelo de datos
y checklist de credenciales de plataformas.

---

## 1. Visión del producto

Tienda online que vende **códigos de gift card digitales** de dos verticales:

| Categoría | Plataformas (productos) |
|---|---|
| `gaming` | Steam, PlayStation Store, Xbox / Microsoft, Nintendo eShop, Google Play, Apple/iTunes, Roblox, Free Fire, Riot Points, Razer Gold, Blizzard Battle.net |
| `cloud_storage` | Google One, Microsoft OneDrive, Dropbox, Mega, pCloud, iCloud+, Icedrive, Sync.com |

Cada producto se vende en **variantes** (denominación + región): p. ej.
`Steam Gift Card — $20 — REGIÓN GLOBAL — SC-STEAM-USD20-GLOBAL`.

Reglas:

- Al comprar, el cliente recibe un **código** (inventariado y cifrado en la BD) entregado
  por correo y visible en su cuenta. `product fulfillment: "code"`.
- Moneda de precios: **USD**. Moneda de cobro: **USDT (Binance Pay)**.

---

## 2. Fases del proyecto

### Fase 1 — Backend + BD (ESTE ENTREGABLE) ✅
- [x] Estructura del backend FastAPI, modelos y esquema de PostgreSQL.
- [x] Autenticación JWT con roles (customer / admin).
- [x] Catálogo público: productos + variantes.
- [x] Carrito simple → creación de pedidos con **reserva atómica** de códigos.
- [x] Inventario de códigos **cifrados** (Fernet).
- [x] Integración **Binance Pay (USDT)**: creación de orden, firma HMAC-SHA512, webhook y verificación de estado.
- [x] Entrega de códigos por correo (SMTP configurable).
- [x] Endpoints admin: productos, carga de códigos, pedidos, pagos.
- [ ] Credenciales reales en `.env` → **pendiente del operador** (checklist abajo).

### Fase 2 — Frontend / Web
- [ ] Tienda SPA (React/Next.js o Astro) consumiendo esta API.
- [ ] Panel admin web (listados, subida masiva de códigos por CSV).
- [ ] Página de "esperando pago" que consulta el estado del pago y redirige a Binance.

### Fase 3 — Expansión comercial
- [ ] Pasarelas adicionales (la tabla `payments` ya es multi-proveedor: binance_pay | stripe | manual | …).
- [ ] Cupones de descuento y compras de regalo (enviar código a otra persona).
- [ ] Historial favoritos / wishlist.
- [ ] Programa de afiliados/códigos de referido.

### Fase 4 — Operación y hardening
- [ ] Verificación criptográfica completa de webhooks (RSA + desencriptación AES-CBC con la clave privada del merchant).
- [ ] Migraciones formalizadas (Alembic ya está en `requirements.txt`; generar `alembic revision` al primer cambio de esquema).
- [ ] Backups automáticos de PostgreSQL, monitoreo (Sentry), rate-limiting.
- [ ] CI/CD y despliegue (Docker Compose + reverse proxy).
- [ ] Reportes: ventas por plataforma, márgenes, conversión.

---

## 3. Flujo de compra con Binance Pay (USDT)

```
 Cliente                    Backend (FastAPI)                      Binance Pay
   │                              │                                    │
   │ POST /orders                 │                                    │
   │─────────────────────────────▶│ valida stock y RESERVA códigos     │
   │  ← order_id, status=pending  │                                    │
   │                              │                                    │
   │ POST /payments/order/{id}    │                                    │
   │─────────────────────────────▶│ POST /binancepay/openapi/v2/order  │
   │                              │  headers: Timestamp, Nonce,        │
   │                              │  Certificate-SN(API Key),          │
   │                              │  Signature(HMAC-SHA512)            │
   │                              │───────────────────────────────────▶│
   │  ← checkoutUrl               │  ← prepayId + checkoutUrl          │
   │───────────────────────────────────────────────────────────────────▶│
   │        (el cliente paga con USDT en la app Binance)               │
   │                              │                                    │
   │                              │ ◀─── webhook: POST …/webhook/… ────│
   │                              │ valida firma, busca payment por    │
   │                              │ merchantTradeNo, marca CONFIRMADO  │
   │                              │ asigna códigos (AVAILABLE→SOLD)    │
   │                              │ envía correos con los códigos      │
   │  GET /orders/{id}            │ order → PAID → DELIVERED           │
   │─────────────────────────────▶│                                    │
```

**Defensas del flujo:**
- Si el webhook falla, `POST /payments/{payment_id}/check` consulta el estado a Binance
  (`/binancepay/openapi/v2/order/query`) y completa el flujo igual.
- Las reservas expiran en `ORDER_RESERVATION_MINUTES` (15) → pedido `expired` si no paga.
- Todo webhook recibido se guarda crudo en `webhook_events` (auditoría / re-procesamiento).
- Un pago nunca se confirma dos veces: el estado `confirmed` es idempotente.

---

## 4. Modelo de datos

```
┌──────────────┐        ┌───────────────────┐        ┌──────────────────┐
│ users        │        │ products          │        │ product_variants │
│──────────────│        │───────────────────│        │──────────────────│
│ id PK        │───1:N─▶│ id PK             │───1:N─▶│ id PK            │
│ email UQ     │        │ slug UQ           │        │ product_id FK    │
│ password_hash│        │ category(gaming|  │        │ denomination     │
│ role(customer│        │  cloud_storage)   │        │ currency USD     │
│  |admin)     │        │ platform(steam…)  │        │ region (GLOBAL…) │
│ is_active    │        │ is_published     │        │ sku UQ           │
└──────┬───────┘        │ image_url         │        │ price_usd        │
       │                └───────────────────┘        │ is_active        │
       │                                             └────────┬─────────┘
       │ N                                                      │ 1
┌──────▼───────┐         ┌──────────────┐              ┌────────▼─────────┐
│ orders       │         │ order_items  │              │ gift_card_codes  │
│──────────────│         │──────────────│              │──────────────────│
│ id PK        │──1:N───▶│ order_id FK  │              │ id PK            │
│ order_number │         │ variant_id FK│              │ variant_id FK    │
│ user_id FK   │         │ quantity     │              │ code_encrypted ←Fernet
│ status:      │         │ unit_price   │              │ status:          │
│  pending     │         │ line_total   │              │  available       │
│  awaiting_pay│         └──────────────┘              │  reserved        │
│  paid        │                                       │  sold            │
│  delivered   │                                       │  void            │
│  cancelled   │                                       │ order_id FK (nulo hasta venta)
│  expired     │                                       │ reserved_until   │
│ total_usd    │                                       └──────────────────┘
└──────┬───────┘
       │ 1                         ┌─────────────────┐
       │ N                         │ webhook_events  │
┌──────▼──────────┐                │─────────────────│
│ payments        │                │ id, provider,   │
│─────────────────│                │ headers, payload│
│ order_id FK     │                │ received_at,    │
│ provider        │                │ processed_at,   │
│ method (USDT)   │                │ status          │
│ status: created │                └─────────────────┘
│  |confirmed     │
│  |failed|expired│   ┌────────────┐
│ prepay_id       │   │ settings   │  clave/valor editable por admin
│ merchant_trade_no UQ┌│────────────│  (contacto, textos, tasas…)
│ checkout_url    │   │ id,key,value│
│ amount_usd      │   └────────────┘
│ raw_request /   │
│ raw_response JSON│
└─────────────────┘
```

Notas de integridad:

- `gift_card_codes` es la **fuente única de inventario**: reservar/entregar se hace con
  `SELECT … FOR UPDATE` (bloqueo pesimista) para que dos compras concurrentes no
  asignen el mismo código.
- Los códigos nunca viajan en claro ni en listados; solo el dueño del pedido los ve descifrados.
- `ON DELETE` de pedidos/items/variantes es `CASCADE` solo en tablas dependientes; un
  código vendido nunca se borra si tiene `order_id`.

---

## 5. Endpoints principales (API v1 — `/api/v1`)

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| POST | `/auth/register` | — | Registro de cliente (rol customer) |
| POST | `/auth/login` | — | Devuelve JWT |
| GET | `/auth/me` | JWT | Perfil del usuario autenticado |
| GET | `/catalog/products` | — | Catálogo filtrable (categoría, plataforma, activo) |
| GET | `/catalog/products/{slug}` | — | Detalle con variantes y stock disponible |
| POST | `/orders` | JWT | Crear pedido (reserva inventario) |
| GET | `/orders` | JWT | Mis pedidos |
| GET | `/orders/{id}` | JWT | Detalle → códigos solo si `paid/delivered` |
| POST | `/payments/order/{order_id}` | JWT | Crear cobro Binance Pay → `checkoutUrl` |
| POST | `/payments/webhook/binance` | Firma | Webhook de Binance Pay |
| POST | `/payments/{id}/check` | JWT | Verificar estado del pago contra Binance |
| Admin | `/admin/products…`, `/admin/orders…`, `/admin/payments…` | JWT+admin | Gestión completa |

---

## 6. Checklist de credenciales de plataformas

Colocar cada una en `.env` (ver `.env.example`). El backend de igual modo arranca;
los módulos que dependen de una credencial devuelven un error descriptivo hasta que exista.

- [ ] `DATABASE_URL` — PostgreSQL local/servidor
- [ ] `APP_SECRET_KEY` — secretos JWT
- [ ] `CODE_ENCRYPTION_KEY` — clave Fernet de códigos
- [ ] `BINANCE_PAY_API_KEY` + `BINANCE_PAY_API_SECRET` — portal Binance Merchant
- [ ] `BINANCE_PAY_BASE_URL` — producción `https://api.binance.com`
- [ ] Registrar el webhook en el portal: `https://tu-dominio/api/v1/payments/webhook/binance`
- [ ] (Opcional, Fase 4) `BINANCE_PAY_MERCHANT_PRIVATE_KEY` — RSA para desencriptar payload del webhook
- [ ] `SMTP_*` — cuenta de correo para envío de códigos
- [ ] `PUBLIC_BASE_URL` — dominio de la web
