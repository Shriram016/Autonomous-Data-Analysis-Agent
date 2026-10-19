"""M0.5 check: the profile report exists, covers all 10 areas, and matches the database.

Run from backend/ after profile_olist:  uv run python dev_checks/check_data_profile.py
"""

import psycopg

from adaa.ingestion.profile_olist import AREAS, GENERATED_MARKER, REPORT
from adaa.settings import get_settings

AREA_TITLES = [
    "1. Basic shape",
    "2. Time range",
    "3. Duplicates",
    "4. Customers",
    "5. Missing links",
    "6. Revenue trap",
    "7. Order status",
    "8. Delivery",
    "9. Reviews",
    "10. Strange values",
]


def main() -> None:
    text = REPORT.read_text(encoding="utf-8")
    assert GENERATED_MARKER in text, "report has no generated section"
    assert len(AREAS) == len(AREA_TITLES)
    for title in AREA_TITLES:
        assert f"## {title}" in text, f"missing section: {title}"
    print(f"OK  all {len(AREA_TITLES)} areas present in {REPORT.name}")

    with psycopg.connect(get_settings().postgres_conninfo("loader")) as conn:
        row = conn.execute("SELECT count(*) FROM business.orders").fetchone()
    orders = row[0] if row else 0
    assert f"| orders | {orders:,} |" in text, "orders row count in report differs from database"
    print(f"OK  report matches the database ({orders:,} orders)")
    print("M0.5 data profile check passed.")


if __name__ == "__main__":
    main()
