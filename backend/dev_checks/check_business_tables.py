"""M0.4 check: the business schema holds the real Olist data, faithful but typed.

Run from backend/ after load_olist:  uv run python dev_checks/check_business_tables.py
"""

import json

import psycopg

from adaa.ingestion.load_olist import TABLES
from adaa.ingestion.prepare_olist import RAW_DIR
from adaa.settings import get_settings

# (table, column) → the type it must have
TYPE_CHECKS = {
    ("orders", "order_purchase_timestamp"): "timestamp without time zone",
    ("order_items", "price"): "numeric",
    ("payments", "payment_value"): "numeric",
    ("customers", "customer_zip_code_prefix"): "text",
    ("reviews", "review_score"): "integer",
    ("geolocation", "geolocation_lat"): "double precision",
}


def scalar(conn: psycopg.Connection, query: str) -> object:
    row = conn.execute(query).fetchone()
    assert row is not None
    return row[0]


def main() -> None:
    manifest = json.loads((RAW_DIR / "olist" / "manifest.json").read_text())
    with psycopg.connect(get_settings().postgres_conninfo("loader")) as conn:
        for table, csv_name in TABLES.items():
            rows = scalar(conn, f"SELECT count(*) FROM business.{table}")
            assert rows == manifest[csv_name]["rows"], f"{table}: {rows} rows"
            owner = scalar(
                conn,
                f"SELECT tableowner FROM pg_tables WHERE schemaname='business' "
                f"AND tablename='{table}'",
            )
            assert owner == "adaa_loader", f"{table} owned by {owner}"
            print(f"OK  business.{table:22} {rows:>9,} rows  (owner {owner})")

        for (table, column), expected in TYPE_CHECKS.items():
            actual = scalar(
                conn,
                "SELECT data_type FROM information_schema.columns WHERE table_schema='business' "
                f"AND table_name='{table}' AND column_name='{column}'",
            )
            assert actual == expected, f"{table}.{column} is {actual}"
        print(f"OK  column types ({len(TYPE_CHECKS)} checked)")

        zeros = scalar(
            conn, "SELECT count(*) FROM business.customers WHERE customer_zip_code_prefix LIKE '0%'"
        )
        assert isinstance(zeros, int) and zeros > 0
        print(f"OK  {zeros:,} customer zip prefixes keep their leading zero")

        undelivered = scalar(
            conn, "SELECT count(*) FROM business.orders WHERE order_delivered_customer_date IS NULL"
        )
        print(f"OK  {undelivered:,} orders have no delivery date (NULL, kept as-is)")

        staging_left = scalar(conn, "SELECT count(*) FROM pg_tables WHERE schemaname='staging'")
        assert staging_left == 0, "staging should be empty after publish"
    print("M0.4 business tables check passed.")


if __name__ == "__main__":
    main()
