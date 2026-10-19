"""Load tiny Olist-shaped CSVs into throwaway schemas and check the "faithful but typed" rule.

Uses its own schemas (test_staging, test_business), so the real business tables are untouched.
Needs: docker compose up, and `python -m adaa.db.roles` run once.
"""

import csv
import json
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest

from adaa.ingestion.load_olist import TABLES, LoadValidationError, load_olist
from adaa.ingestion.prepare_olist import EXPECTED_FILES, describe
from adaa.settings import get_settings

pytestmark = pytest.mark.integration

STAGING, TARGET = "test_staging", "test_business"
TS = "2017-10-02 10:56:33"

# One small, realistic row set per table (values in CSV column order).
ROWS: dict[str, list[list[str]]] = {
    "customers": [["c1", "u1", "01310", "sao paulo", "SP"]],  # zip with a leading zero
    "geolocation": [["01310", "-23.56", "-46.65", "sao paulo", "SP"]] * 2,  # zip repeats
    "orders": [
        ["o1", "c1", "delivered", TS, TS, TS, TS, TS],
        ["o2", "c1", "shipped", TS, TS, TS, "", TS],  # not delivered yet: empty date
    ],
    "order_items": [["o1", "1", "p1", "s1", TS, "58.90", "13.29"]],
    "payments": [["o1", "1", "credit_card", "8", "72.19"]],
    "reviews": [
        ["r1", "o1", "5", "", "Muito bom\nrecomendo", TS, TS],  # comment on two lines
        ["r1", "o2", "4", "", "", TS, TS],  # review_id repeats, as in the real data
    ],
    "products": [["p1", "perfumaria", "40", "287", "1", "225", "16", "10", "14"]],
    "sellers": [["s1", "09350", "maua", "SP"]],
    "category_translation": [["perfumaria", "perfumery"]],
}


def write_fixture(folder: Path, drop_row_from: str | None = None) -> Path:
    """Write the 9 CSVs + manifest.json. Optionally make one CSV disagree with its manifest."""
    manifest = {}
    for table, csv_name in TABLES.items():
        path = folder / csv_name
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(EXPECTED_FILES[csv_name])
            writer.writerows(ROWS[table])
        manifest[csv_name] = describe(path, EXPECTED_FILES[csv_name])
    if drop_row_from:
        rows = manifest[TABLES[drop_row_from]]["rows"]
        assert isinstance(rows, int)
        manifest[TABLES[drop_row_from]]["rows"] = rows + 1  # manifest expects one row more
    (folder / "manifest.json").write_text(json.dumps(manifest))
    return folder


@pytest.fixture
def owner() -> Iterator[psycopg.Connection]:
    with psycopg.connect(get_settings().postgres_conninfo("owner"), autocommit=True) as conn:
        for schema in (STAGING, TARGET):
            conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            conn.execute(f"CREATE SCHEMA {schema}")
            conn.execute(f"GRANT USAGE, CREATE ON SCHEMA {schema} TO adaa_loader")
        yield conn
        for schema in (STAGING, TARGET):
            conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")


def load(folder: Path) -> dict[str, int]:
    return load_olist(
        get_settings().postgres_conninfo("loader"), folder, staging=STAGING, target=TARGET
    )


def test_faithful_but_typed(owner: psycopg.Connection, tmp_path: Path) -> None:
    counts = load(write_fixture(tmp_path))
    assert counts["reviews"] == 2 and counts["geolocation"] == 2

    def one(query: str) -> tuple:
        row = owner.execute(query).fetchone()
        assert row is not None
        return tuple(row)

    assert one(f"SELECT customer_zip_code_prefix FROM {TARGET}.customers") == ("01310",)
    assert one(f"SELECT price FROM {TARGET}.order_items") == (Decimal("58.90"),)
    assert one(
        f"SELECT order_delivered_customer_date IS NULL FROM {TARGET}.orders WHERE order_id='o2'"
    ) == (True,)
    assert one(f"SELECT review_comment_message FROM {TARGET}.reviews WHERE order_id='o1'") == (
        "Muito bom\nrecomendo",
    )
    assert one(
        f"SELECT data_type FROM information_schema.columns WHERE table_schema='{TARGET}' "
        "AND table_name='orders' AND column_name='order_purchase_timestamp'"
    ) == ("timestamp without time zone",)
    assert one(f"SELECT tableowner FROM pg_tables WHERE schemaname='{TARGET}' LIMIT 1") == (
        "adaa_loader",
    )
    assert one(f"SELECT count(*) FROM pg_tables WHERE schemaname='{STAGING}'") == (0,)


def test_mismatch_publishes_nothing(owner: psycopg.Connection, tmp_path: Path) -> None:
    with pytest.raises(LoadValidationError, match="reviews"):
        load(write_fixture(tmp_path, drop_row_from="reviews"))
    row = owner.execute(f"SELECT count(*) FROM pg_tables WHERE schemaname='{TARGET}'").fetchone()
    assert row == (0,)  # target schema still empty: nothing was published
