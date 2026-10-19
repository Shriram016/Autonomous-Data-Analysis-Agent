"""Load the prepared Olist CSVs into Postgres: staging → validate → atomic publish.

1. Recreate the 9 tables in the staging schema (types from sql/olist_tables.sql).
2. Bulk-load each CSV with COPY.
3. Compare every table's row count with manifest.json; on any mismatch, stop — nothing is
   published and the current business tables stay as they were.
4. In ONE transaction, move the staging tables into the business schema, replacing the old
   ones. Readers see all old data or all new data, never a mix.

Runs as adaa_loader. Run from backend/:  uv run python -m adaa.ingestion.load_olist
"""

import json
from pathlib import Path

import psycopg
from psycopg import sql

from adaa.ingestion.prepare_olist import EXPECTED_FILES, RAW_DIR
from adaa.settings import get_settings

SCHEMA_SQL = Path(__file__).parent / "sql" / "olist_tables.sql"

# Table name → CSV file it is loaded from.
TABLES: dict[str, str] = {
    "customers": "olist_customers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}

COPY_CHUNK_BYTES = 1 << 20  # stream files in 1 MiB pieces


class LoadValidationError(Exception):
    """Staging doesn't match the manifest; nothing was published."""


def create_staging_tables(conn: psycopg.Connection, staging: str) -> None:
    for table in TABLES:
        conn.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(staging, table)))
    conn.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(staging)))
    conn.execute(SCHEMA_SQL.read_text())


def copy_csv(conn: psycopg.Connection, staging: str, table: str, csv_path: Path) -> None:
    columns = sql.SQL(", ").join(sql.Identifier(c) for c in EXPECTED_FILES[TABLES[table]])
    # CSV format: unquoted empty cells become NULL; HEADER skips the first line.
    statement = sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT csv, HEADER true)").format(
        sql.Identifier(staging, table), columns
    )
    with conn.cursor().copy(statement) as copy, csv_path.open("rb") as f:
        while chunk := f.read(COPY_CHUNK_BYTES):
            copy.write(chunk)


def staged_row_counts(conn: psycopg.Connection, staging: str) -> dict[str, int]:
    counts = {}
    for table in TABLES:
        query = sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(staging, table))
        row = conn.execute(query).fetchone()
        counts[table] = row[0] if row else 0
    return counts


def validate(counts: dict[str, int], manifest: dict[str, dict[str, int]]) -> None:
    problems = [
        f"{table}: loaded {counts[table]:,}, manifest says {manifest[csv]['rows']:,}"
        for table, csv in TABLES.items()
        if counts[table] != manifest[csv]["rows"]
    ]
    if problems:
        raise LoadValidationError("Not published. " + "; ".join(problems))


def publish(conn: psycopg.Connection, staging: str, target: str) -> None:
    """Swap staging tables into the target schema. Caller runs this in one transaction."""
    for table in TABLES:
        conn.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(target, table)))
        conn.execute(
            sql.SQL("ALTER TABLE {} SET SCHEMA {}").format(
                sql.Identifier(staging, table), sql.Identifier(target)
            )
        )


def load_olist(
    conninfo: str,
    olist_dir: Path = RAW_DIR / "olist",
    staging: str = "staging",
    target: str = "business",
) -> dict[str, int]:
    manifest = json.loads((olist_dir / "manifest.json").read_text())
    with psycopg.connect(conninfo) as conn:
        with conn.transaction():  # 1–2: load into staging
            create_staging_tables(conn, staging)
            for table, csv_name in TABLES.items():
                copy_csv(conn, staging, table, olist_dir / csv_name)
        counts = staged_row_counts(conn, staging)
        validate(counts, manifest)  # 3: raises before anything is published
        with conn.transaction():  # 4: atomic publish
            publish(conn, staging, target)
    return counts


def main() -> None:
    counts = load_olist(get_settings().postgres_conninfo("loader"))
    for table, rows in counts.items():
        print(f"business.{table:22} {rows:>9,} rows")
    print("Loaded, validated against manifest.json, and published to schema business.")


if __name__ == "__main__":
    main()
