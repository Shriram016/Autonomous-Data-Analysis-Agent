"""Profile the Olist tables and write docs/data-profile.md.

SQL does the measuring inside Postgres; Python only sends the queries and formats the results
as Markdown. Read-only: nothing in the database changes. The report holds counts and
percentages only, never customer rows or IDs.

Hand-written findings above the GENERATED_MARKER line are kept when the script runs again;
everything below the marker is replaced.

Run from backend/:  uv run python -m adaa.ingestion.profile_olist
"""

from collections.abc import Callable, Sequence
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg

from adaa.ingestion.load_olist import TABLES
from adaa.settings import REPO_ROOT, get_settings

REPORT = REPO_ROOT / "docs" / "data-profile.md"
GENERATED_MARKER = "<!-- GENERATED BELOW: do not edit by hand; rerun profile_olist -->"
THIN_MONTH_ORDERS = 500  # months with fewer orders than this are too thin to trust


# ---------- helpers ----------


def fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float | Decimal):
        return f"{value:,.2f}"
    return str(value)


def table(conn: psycopg.Connection, query: str) -> str:
    """Run a query and render the result as a Markdown table."""
    cur = conn.execute(query)
    headers = [col.name for col in cur.description or []]
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(fmt(v) for v in row) + " |" for row in cur.fetchall()]
    return "\n".join(lines)


def section(title: str, *parts: str) -> str:
    return f"## {title}\n\n" + "\n\n".join(parts)


# ---------- the 10 areas ----------


def in_order(selects: list[str], columns: str) -> str:
    """UNION ALL keeps no order, so number each SELECT and sort by that number."""
    numbered = " UNION ALL ".join(f"SELECT {i} AS n, {s}" for i, s in enumerate(selects))
    return f"SELECT {columns} FROM ({numbered}) u ORDER BY n"


def basic_shape(conn: psycopg.Connection) -> str:
    """Rows per table, and empty (NULL) share + distinct values per column."""
    rows_query = in_order(
        [f"'{t}' AS \"table\", count(*) AS rows FROM business.{t}" for t in TABLES],
        '"table", rows',
    )
    parts = [table(conn, rows_query)]
    for t in TABLES:
        cols = conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'business' AND table_name = %s ORDER BY ordinal_position",
            (t,),
        ).fetchall()
        column_query = in_order(
            [
                f"'{c}' AS \"column\", '{dt}' AS type, "
                f"round(100.0 * (count(*) - count({c})) / count(*), 1) AS null_pct, "
                f"count(DISTINCT {c}) AS distinct_values FROM business.{t}"
                for c, dt in cols
            ],
            '"column", type, null_pct, distinct_values',
        )
        parts.append(f"**{t}**\n\n" + table(conn, column_query))
    return section("1. Basic shape", *parts)


def time_range(conn: psycopg.Connection) -> str:
    span = table(
        conn,
        "SELECT min(order_purchase_timestamp) AS first_order, "
        "max(order_purchase_timestamp) AS last_order FROM business.orders",
    )
    months = table(
        conn,
        "SELECT to_char(date_trunc('month', order_purchase_timestamp), 'YYYY-MM') AS month, "
        f"count(*) AS orders, count(*) < {THIN_MONTH_ORDERS} AS thin "
        "FROM business.orders GROUP BY 1 ORDER BY 1",
    )
    return section(
        "2. Time range", span, f"Orders per month (thin = fewer than {THIN_MONTH_ORDERS}):", months
    )


def duplicates(conn: psycopg.Connection) -> str:
    return section(
        "3. Duplicates",
        table(
            conn,
            "SELECT count(*) AS review_ids_used_more_than_once, "
            "coalesce(sum(n), 0)::bigint AS rows_involved "
            "FROM (SELECT count(*) AS n FROM business.reviews GROUP BY review_id "
            "HAVING count(*) > 1) d",
        ),
        table(
            conn,
            "SELECT count(*) FILTER (WHERE n > 1) AS orders_with_2plus_reviews, "
            "(SELECT count(*) FROM business.orders o WHERE NOT EXISTS "
            "(SELECT 1 FROM business.reviews r WHERE r.order_id = o.order_id)) "
            "AS orders_with_no_review "
            "FROM (SELECT order_id, count(*) AS n FROM business.reviews GROUP BY order_id) x",
        ),
    )


def customers(conn: psycopg.Connection) -> str:
    return section(
        "4. Customers",
        table(
            conn,
            "SELECT count(DISTINCT customer_id) AS customer_ids, "
            "count(DISTINCT customer_unique_id) AS real_people FROM business.customers",
        ),
        table(
            conn,
            "SELECT count(*) FILTER (WHERE n > 1) AS people_with_2plus_orders, "
            "round(100.0 * count(*) FILTER (WHERE n > 1) / count(*), 1) AS pct_repeat "
            "FROM (SELECT c.customer_unique_id, count(*) AS n FROM business.orders o "
            "JOIN business.customers c USING (customer_id) GROUP BY 1) x",
        ),
    )


def missing_links(conn: psycopg.Connection) -> str:
    checks = {
        "products with no category": (
            "SELECT count(*) FROM business.products WHERE product_category_name IS NULL"
        ),
        "categories with no English name": (
            "SELECT count(DISTINCT p.product_category_name) FROM business.products p "
            "LEFT JOIN business.category_translation t USING (product_category_name) "
            "WHERE p.product_category_name IS NOT NULL AND t.product_category_name IS NULL"
        ),
        "order items whose product is missing": (
            "SELECT count(*) FROM business.order_items i "
            "LEFT JOIN business.products p USING (product_id) WHERE p.product_id IS NULL"
        ),
        "orders with no items": (
            "SELECT count(*) FROM business.orders o WHERE NOT EXISTS "
            "(SELECT 1 FROM business.order_items i WHERE i.order_id = o.order_id)"
        ),
        "orders with no payment": (
            "SELECT count(*) FROM business.orders o WHERE NOT EXISTS "
            "(SELECT 1 FROM business.payments p WHERE p.order_id = o.order_id)"
        ),
        "reviews whose order is missing": (
            "SELECT count(*) FROM business.reviews r LEFT JOIN business.orders o "
            "USING (order_id) WHERE o.order_id IS NULL"
        ),
        "customer zip prefixes not in geolocation": (
            "SELECT count(DISTINCT customer_zip_code_prefix) FROM business.customers c "
            "WHERE NOT EXISTS (SELECT 1 FROM business.geolocation g "
            "WHERE g.geolocation_zip_code_prefix = c.customer_zip_code_prefix)"
        ),
    }
    query = in_order(
        [f"'{name}' AS check, ({sql}) AS count" for name, sql in checks.items()],
        '"check", count',  # "check" is a reserved word, so it needs quotes here
    )
    untranslated = table(
        conn,
        "SELECT DISTINCT p.product_category_name AS untranslated_category FROM business.products p "
        "LEFT JOIN business.category_translation t USING (product_category_name) "
        "WHERE p.product_category_name IS NOT NULL AND t.product_category_name IS NULL ORDER BY 1",
    )
    return section("5. Missing links", table(conn, query), untranslated)


def revenue_trap(conn: psycopg.Connection) -> str:
    """Item price + freight vs payment value, per order."""
    per_order = (
        "WITH items AS (SELECT order_id, sum(price + freight_value) AS items_total "
        "FROM business.order_items GROUP BY 1), "
        "pays AS (SELECT order_id, sum(payment_value) AS paid_total "
        "FROM business.payments GROUP BY 1) "
    )
    return section(
        "6. Revenue trap",
        table(
            conn,
            per_order + "SELECT count(*) AS orders_with_both, "
            "count(*) FILTER (WHERE abs(items_total - paid_total) <= 0.01) AS equal, "
            "count(*) FILTER (WHERE abs(items_total - paid_total) > 0.01) AS different, "
            "round(100.0 * count(*) FILTER (WHERE abs(items_total - paid_total) > 0.01) "
            "/ count(*), 1) AS pct_different, "
            "max(abs(items_total - paid_total)) AS max_difference "
            "FROM items JOIN pays USING (order_id)",
        ),
        table(
            conn,
            "SELECT (SELECT sum(price) FROM business.order_items) AS sum_item_price, "
            "(SELECT sum(freight_value) FROM business.order_items) AS sum_freight, "
            "(SELECT sum(payment_value) FROM business.payments) AS sum_payment_value",
        ),
    )


def order_status(conn: psycopg.Connection) -> str:
    return section(
        "7. Order status",
        table(
            conn,
            "SELECT order_status, count(*) AS orders, "
            "round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS pct "
            "FROM business.orders GROUP BY 1 ORDER BY 2 DESC",
        ),
        table(
            conn,
            "SELECT count(*) FILTER (WHERE order_status = 'delivered' "
            "AND order_delivered_customer_date IS NULL) AS delivered_but_no_delivery_date, "
            "count(*) FILTER (WHERE order_status <> 'delivered' "
            "AND order_delivered_customer_date IS NOT NULL) AS not_delivered_but_has_date "
            "FROM business.orders",
        ),
    )


def delivery(conn: psycopg.Connection) -> str:
    late = "order_delivered_customer_date::date > order_estimated_delivery_date::date"
    days_late = "(order_delivered_customer_date::date - order_estimated_delivery_date::date)"
    base = (
        "FROM business.orders WHERE order_status = 'delivered' "
        "AND order_delivered_customer_date IS NOT NULL"
    )
    return section(
        "8. Delivery",
        table(
            conn,
            f"SELECT count(*) AS delivered_with_date, count(*) FILTER (WHERE {late}) AS late, "
            f"round(100.0 * count(*) FILTER (WHERE {late}) / count(*), 1) AS pct_late, "
            f"round(avg({days_late}) FILTER (WHERE {late}), 1) AS avg_days_late_when_late, "
            "round(avg(order_delivered_customer_date::date - order_purchase_timestamp::date), 1) "
            f"AS avg_days_to_deliver {base}",
        ),
        table(
            conn,
            f"SELECT CASE WHEN {days_late} <= 0 THEN 'on time or early' "
            f"WHEN {days_late} <= 7 THEN '1-7 days late' "
            f"WHEN {days_late} <= 30 THEN '8-30 days late' ELSE 'over 30 days late' END AS bucket, "
            f"count(*) AS orders {base} GROUP BY 1 ORDER BY min({days_late})",
        ),
    )


def reviews(conn: psycopg.Connection) -> str:
    return section(
        "9. Reviews",
        table(
            conn,
            "SELECT count(*) AS reviews, "
            "round(100.0 * count(review_comment_title) / count(*), 1) AS pct_with_title, "
            "round(100.0 * count(review_comment_message) / count(*), 1) AS pct_with_comment, "
            "round(avg(length(review_comment_message)), 0) AS avg_comment_chars, "
            "percentile_cont(0.5) WITHIN GROUP (ORDER BY length(review_comment_message)) "
            "AS median_comment_chars FROM business.reviews",
        ),
        table(
            conn,
            "SELECT review_score, count(*) AS reviews, "
            "round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct_of_reviews, "
            "round(100.0 * count(review_comment_message) / count(*), 1) AS pct_with_comment "
            "FROM business.reviews GROUP BY 1 ORDER BY 1",
        ),
    )


def strange_values(conn: psycopg.Connection) -> str:
    checks = {
        "payments with value 0": "SELECT count(*) FROM business.payments WHERE payment_value = 0",
        "payments with 0 instalments": (
            "SELECT count(*) FROM business.payments WHERE payment_installments = 0"
        ),
        "payments with type not_defined": (
            "SELECT count(*) FROM business.payments WHERE payment_type = 'not_defined'"
        ),
        "items where freight > price": (
            "SELECT count(*) FROM business.order_items WHERE freight_value > price"
        ),
        "products with no weight": (
            "SELECT count(*) FROM business.products WHERE product_weight_g IS NULL"
        ),
        "geolocation points outside Brazil": (
            "SELECT count(*) FROM business.geolocation WHERE geolocation_lat NOT BETWEEN -33.8 "
            "AND 5.3 OR geolocation_lng NOT BETWEEN -74.0 AND -34.7"
        ),
    }
    query = in_order(
        [f"'{name}' AS check, ({sql}) AS count" for name, sql in checks.items()],
        '"check", count',
    )
    prices = table(
        conn,
        "SELECT min(price) AS min_price, "
        "percentile_cont(0.5) WITHIN GROUP (ORDER BY price) AS median_price, "
        "max(price) AS max_price, max(freight_value) AS max_freight FROM business.order_items",
    )
    return section("10. Strange values", table(conn, query), prices)


AREAS: Sequence[Callable[[psycopg.Connection], str]] = (
    basic_shape,
    time_range,
    duplicates,
    customers,
    missing_links,
    revenue_trap,
    order_status,
    delivery,
    reviews,
    strange_values,
)


# ---------- report ----------


def build_report(conn: psycopg.Connection) -> str:
    sections = [area(conn) for area in AREAS]
    header = f"*Generated {date.today().isoformat()} from schema `business`.*"
    return "\n\n".join([header, *sections]) + "\n"


def write_report(generated: str) -> None:
    """Keep hand-written text above the marker; replace everything below it."""
    above = (
        "# Olist data profile\n\n## Findings and impact\n\n(Written after reading the numbers.)\n"
    )
    if REPORT.exists() and GENERATED_MARKER in REPORT.read_text(encoding="utf-8"):
        above = REPORT.read_text(encoding="utf-8").split(GENERATED_MARKER)[0].rstrip() + "\n"
    REPORT.write_text(f"{above}\n{GENERATED_MARKER}\n\n{generated}", encoding="utf-8")


def main() -> None:
    with psycopg.connect(get_settings().postgres_conninfo("loader")) as conn:
        generated = build_report(conn)
    write_report(generated)
    print(f"Wrote {REPORT} ({len(AREAS)} areas).")


if __name__ == "__main__":
    main()
