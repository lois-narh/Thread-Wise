-- Workspace schema.
-- customers 1--* orders *--1 tailors
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS tailors;

CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    city        TEXT,
    phone       TEXT,
    joined_date TEXT
);

CREATE TABLE tailors (
    tailor_id        INTEGER PRIMARY KEY,
    name             TEXT NOT NULL,
    skill_level      TEXT,      -- Junior / Mid / Senior
    years_experience INTEGER
);

-- order_id is deliberately NOT unique: real shop ledgers contain duplicate entries,
-- and the data-quality checks need something to find.
CREATE TABLE orders (
    order_id       TEXT NOT NULL,
    customer_id    INTEGER REFERENCES customers(customer_id),
    tailor_id      INTEGER REFERENCES tailors(tailor_id),
    order_date     TEXT NOT NULL,
    promised_date  TEXT NOT NULL,
    delivered_date TEXT,        -- NULL while the order is still in progress
    garment_type   TEXT,
    fabric_source  TEXT,        -- Shop / Customer
    complexity     INTEGER,     -- 1 (shirt) .. 5 (wedding gown)
    is_rush        INTEGER,
    occasion       TEXT,        -- Funeral, Christmas, Easter, Eid, ...
    price_ghs      REAL,
    deposit_ghs    REAL,
    status         TEXT         -- Delivered / In progress
);
CREATE INDEX idx_orders_order_id ON orders(order_id);
CREATE INDEX idx_orders_tailor_date ON orders(tailor_id, order_date);