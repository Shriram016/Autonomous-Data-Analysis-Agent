-- Olist tables, "faithful but typed" (§0 M0.4): same rows and column names as the CSVs
-- (Olist's typos included), correct types, primary keys only where values are unique,
-- no foreign keys, no business rules. Unqualified names: the loader sets search_path
-- to the staging schema before running this file.

CREATE TABLE customers (
    customer_id              text PRIMARY KEY,
    customer_unique_id       text,
    customer_zip_code_prefix text,  -- text: keeps leading zeros ("01310")
    customer_city            text,
    customer_state           text
);

CREATE TABLE geolocation (          -- no key: many rows per zip prefix
    geolocation_zip_code_prefix text,
    geolocation_lat             double precision,
    geolocation_lng             double precision,
    geolocation_city            text,
    geolocation_state           text
);

CREATE TABLE orders (
    order_id                      text PRIMARY KEY,
    customer_id                   text,
    order_status                  text,
    order_purchase_timestamp      timestamp,
    order_approved_at             timestamp,
    order_delivered_carrier_date  timestamp,
    order_delivered_customer_date timestamp,  -- empty for undelivered orders → NULL
    order_estimated_delivery_date timestamp
);

CREATE TABLE order_items (
    order_id            text,
    order_item_id       integer,
    product_id          text,
    seller_id           text,
    shipping_limit_date timestamp,
    price               numeric(10, 2),  -- numeric: exact money, no float rounding
    freight_value       numeric(10, 2),
    PRIMARY KEY (order_id, order_item_id)
);

CREATE TABLE payments (
    order_id             text,
    payment_sequential   integer,
    payment_type         text,
    payment_installments integer,
    payment_value        numeric(10, 2),
    PRIMARY KEY (order_id, payment_sequential)
);

CREATE TABLE reviews (              -- no key: review_id repeats (profiled in M0.5)
    review_id               text,
    order_id                text,
    review_score            integer,
    review_comment_title    text,
    review_comment_message  text,   -- Portuguese; can span several lines
    review_creation_date    timestamp,
    review_answer_timestamp timestamp
);

CREATE TABLE products (
    product_id                 text PRIMARY KEY,
    product_category_name      text,  -- Portuguese; some missing
    product_name_lenght        integer,
    product_description_lenght integer,
    product_photos_qty         integer,
    product_weight_g           integer,
    product_length_cm          integer,
    product_height_cm          integer,
    product_width_cm           integer
);

CREATE TABLE sellers (
    seller_id              text PRIMARY KEY,
    seller_zip_code_prefix text,
    seller_city            text,
    seller_state           text
);

CREATE TABLE category_translation (
    product_category_name         text PRIMARY KEY,
    product_category_name_english text
);
