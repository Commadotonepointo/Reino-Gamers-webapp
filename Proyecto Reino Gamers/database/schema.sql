-- ============================================================
-- Reino Gamers — Esquema de base de datos (PostgreSQL 14+)
-- Referencia DDL. La app también crea esto automáticamente con
-- SQLAlchemy (create_all) al arrancar. Útil para revisión manual
-- o despliegue controlado.
-- ============================================================

-- (Opcional) crear base
-- CREATE DATABASE reino_gamers;
-- \c reino_gamers

CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- gen_random_uuid()

-- ------------------------------------------------------------
-- Usuarios
-- ------------------------------------------------------------
CREATE TYPE user_role AS ENUM ('customer', 'admin');

CREATE TABLE users (
    id            BIGSERIAL PRIMARY KEY,
    email         VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name     VARCHAR(255) NOT NULL DEFAULT '',
    role          user_role    NOT NULL DEFAULT 'customer',
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------
-- Catálogo: productos (plataformas) y variantes (monto/región)
-- ------------------------------------------------------------
CREATE TYPE product_category AS ENUM ('gaming', 'cloud_storage');

CREATE TABLE products (
    id           BIGSERIAL PRIMARY KEY,
    slug         VARCHAR(120)  NOT NULL UNIQUE,
    name         VARCHAR(255)  NOT NULL,
    category     product_category NOT NULL,
    platform     VARCHAR(60)   NOT NULL,          -- steam, google_one, dropbox…
    description  TEXT          NOT NULL DEFAULT '',
    image_url    VARCHAR(500),
    is_active    BOOLEAN       NOT NULL DEFAULT TRUE,
    sort_order   INTEGER       NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX idx_products_category ON products (category);
CREATE INDEX idx_products_platform ON products (platform);

CREATE TABLE product_variants (
    id           BIGSERIAL PRIMARY KEY,
    product_id   BIGINT       NOT NULL REFERENCES products(id)      ON DELETE CASCADE,
    sku          VARCHAR(80)  NOT NULL UNIQUE,                      -- SC-STEAM-USD20-GLOBAL
    denomination NUMERIC(10,2) NOT NULL,                             -- monto nominal de la tarjeta
    currency     VARCHAR(8)   NOT NULL DEFAULT 'USD',
    region       VARCHAR(40)  NOT NULL DEFAULT 'GLOBAL',
    price_usd    NUMERIC(10,2) NOT NULL,                             -- precio de venta
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_variants_product ON product_variants (product_id);

-- ------------------------------------------------------------
-- Inventario de códigos de gift card (CIFRADOS en reposo)
-- ------------------------------------------------------------
CREATE TYPE code_status AS ENUM ('available', 'reserved', 'sold', 'void');

CREATE TABLE gift_card_codes (
    id             BIGSERIAL PRIMARY KEY,
    variant_id     BIGINT      NOT NULL REFERENCES product_variants(id) ON DELETE CASCADE,
    code_encrypted TEXT        NOT NULL,                    -- Fernet (AES128-CBC+HMAC)
    status         code_status NOT NULL DEFAULT 'available',
    order_id       BIGINT,                                  -- setea al vender
    reserved_until TIMESTAMPTZ,
    sold_at        TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Reserva/venta atómica: se bloquea filas available por variante
CREATE INDEX idx_codes_variant_status ON gift_card_codes (variant_id, status);
CREATE INDEX idx_codes_order ON gift_card_codes (order_id);

-- ------------------------------------------------------------
-- Pedidos e ítems
-- ------------------------------------------------------------
CREATE TYPE order_status AS ENUM (
    'pending', 'awaiting_payment', 'paid', 'delivered', 'cancelled', 'expired'
);

CREATE TABLE orders (
    id              BIGSERIAL PRIMARY KEY,
    order_number    VARCHAR(30)  NOT NULL UNIQUE,           -- RG-20260101-XXXXX
    user_id         BIGINT       NOT NULL REFERENCES users(id),
    status          order_status NOT NULL DEFAULT 'pending',
    delivery_email  VARCHAR(255) NOT NULL,
    subtotal_usd    NUMERIC(10,2) NOT NULL DEFAULT 0,
    total_usd       NUMERIC(10,2) NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    paid_at         TIMESTAMPTZ,
    delivered_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ                             -- fin de la reserva
);
CREATE INDEX idx_orders_user ON orders (user_id);
CREATE INDEX idx_orders_status ON orders (status);

CREATE TABLE order_items (
    id           BIGSERIAL PRIMARY KEY,
    order_id     BIGINT        NOT NULL REFERENCES orders(id)             ON DELETE CASCADE,
    variant_id   BIGINT        NOT NULL REFERENCES product_variants(id),
    product_name VARCHAR(255)  NOT NULL,                     -- snapshot histórico
    variant_sku  VARCHAR(80)   NOT NULL,
    quantity     INTEGER       NOT NULL CHECK (quantity > 0),
    unit_price   NUMERIC(10,2) NOT NULL,
    line_total   NUMERIC(10,2) NOT NULL
);
CREATE INDEX idx_items_order ON order_items (order_id);

-- ------------------------------------------------------------
-- Pagos (multi-pasarela; método principal: binance_pay / USDT)
-- ------------------------------------------------------------
CREATE TYPE payment_provider AS ENUM ('binance_pay', 'manual', 'other');
CREATE TYPE payment_status AS ENUM ('created', 'pending', 'confirmed', 'failed', 'expired');

CREATE TABLE payments (
    id                 BIGSERIAL PRIMARY KEY,
    order_id           BIGINT      NOT NULL REFERENCES orders(id),
    provider           payment_provider NOT NULL,
    method             VARCHAR(20) NOT NULL DEFAULT 'USDT',
    status             payment_status NOT NULL DEFAULT 'created',
    amount_usd         NUMERIC(10,2) NOT NULL,
    currency           VARCHAR(10) NOT NULL DEFAULT 'USDT',
    prepay_id          VARCHAR(120),
    merchant_trade_no  VARCHAR(120) UNIQUE,                 -- nuestro identificador ante Binance
    checkout_url       VARCHAR(500),
    raw_request        JSONB,
    raw_response       JSONB,
    raw_webhook        JSONB,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed_at       TIMESTAMPTZ,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_payments_order ON payments (order_id);
CREATE INDEX idx_payments_status ON payments (provider, status);

-- ------------------------------------------------------------
-- Bitácora de webhooks (auditoría y reproceso)
-- ------------------------------------------------------------
CREATE TABLE webhook_events (
    id           BIGSERIAL PRIMARY KEY,
    provider     VARCHAR(40) NOT NULL,
    headers      JSONB,
    payload      JSONB,
    status       VARCHAR(20) NOT NULL DEFAULT 'received',   -- received|processed|failed
    received_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ
);

-- ------------------------------------------------------------
-- Configuración editable del sitio (para panel admin)
-- ------------------------------------------------------------
CREATE TABLE settings (
    key        VARCHAR(80) PRIMARY KEY,
    value      TEXT        NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
