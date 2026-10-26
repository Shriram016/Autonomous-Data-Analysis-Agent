"""M0.6 check: every metric runs on the real data and matches an independent SQL query.

The SQL here is built only from the YAML definitions (table, sql, filters, join path). The
real compiler comes in M1/M2; this proves the definitions themselves are correct.

Run from backend/:  uv run python dev_checks/check_semantic_layer.py
"""

import psycopg

from adaa.semantic_layer.definitions import Metric, SemanticLayer, load, tables_in
from adaa.settings import get_settings

# Independent hand-written queries (not built from the YAML) for the key definitions.
EXPECTED = {
    "revenue": (
        "SELECT sum(i.price) FROM order_items i JOIN orders o USING (order_id) "
        "WHERE o.order_status = 'delivered'"
    ),
    "late_delivery_rate": (
        "SELECT avg((order_delivered_customer_date::date > order_estimated_delivery_date::date)"
        "::int) FROM orders WHERE order_status = 'delivered' "
        "AND order_delivered_customer_date IS NOT NULL"
    ),
    # v0.5.0: every person, every order status (§0 M2 3c decisions 5 and 6)
    "customers": "SELECT count(DISTINCT customer_unique_id) FROM customers",
    "orders": "SELECT count(*) FROM orders",
    # v0.4.0
    "items_sold": "SELECT count(*) FROM order_items",
    "active_sellers": "SELECT count(DISTINCT seller_id) FROM order_items",
    "cancellation_rate": (
        "SELECT count(*) FILTER (WHERE order_status = 'canceled')::numeric / count(*) FROM orders"
    ),
    "low_review_rate": (
        "SELECT count(*) FILTER (WHERE review_score IN (1, 2))::numeric / count(*) FROM reviews"
    ),
    "repeat_customer_rate": (
        "SELECT avg((n >= 2)::int) FROM (SELECT c.customer_unique_id, count(*) AS n "
        "FROM orders o JOIN customers c USING (customer_id) "
        "GROUP BY c.customer_unique_id) AS people"
    ),
}


def metric_sql(layer: SemanticLayer, m: Metric) -> str:
    # A question with no status gets the D2 default (v0.3.0: a default, not a fixed filter).
    filters = [*m.filters]
    if m.status == "default":
        filters.append(layer.defaults["default_status_filter"].means)
    needed = tables_in(m.sql, m.per or "", m.per_sql or "", *filters) - {m.table}
    joins = " ".join(
        f"{'LEFT JOIN' if j.optional else 'JOIN'} {j.to_table} ON {j.condition}"
        for j in layer.join_path(m.table, needed)
    )
    where = f" WHERE {' AND '.join(filters)}" if filters else ""
    if m.per:  # two steps: one row per person, then the metric over those rows
        inner = f"SELECT {m.per_sql} AS per_value FROM {m.table} {joins}{where} GROUP BY {m.per}"
        return f"SELECT {m.sql} FROM ({inner}) AS per_row"
    return f"SELECT {m.sql} FROM {m.table} {joins}{where}"


def main() -> None:
    layer = load()
    print(f"Loaded semantic layer v{layer.version} (fingerprint {layer.fingerprint[:12]})")
    print(
        f"{len(layer.metrics)} metrics, {len(layer.dimensions)} dimensions, "
        f"{len(layer.joins)} joins, {len(layer.defaults)} defaults\n"
    )
    with psycopg.connect(get_settings().postgres_conninfo("loader")) as conn:
        conn.execute("SET search_path TO business")
        for name, m in layer.metrics.items():
            row = conn.execute(metric_sql(layer, m)).fetchone()
            value = row[0] if row else None
            note = ""
            if name in EXPECTED:
                expected_row = conn.execute(EXPECTED[name]).fetchone()
                assert expected_row is not None and value == expected_row[0], (
                    f"{name}: YAML gives {value}, hand-written SQL gives {expected_row}"
                )
                note = "  OK: matches hand-written SQL"
            assert value is not None, f"{name} returned no value"
            shown = f"{value:,}" if isinstance(value, int) else f"{float(value):,.4f}"
            print(f"{name:22} {shown:>18} {m.unit:6}{note}")

    print("\nGrain rule samples:")
    for metric, dim in [
        ("revenue", "product_category"),
        ("revenue", "payment_type"),
        ("total_paid", "product_category"),
        ("total_paid", "customer_state"),
    ]:
        verdict = "allowed" if layer.can_use(metric, dim) else "refused (would double count)"
        print(f"  {metric} by {dim}: {verdict}")
    print("\nM0.6 semantic layer check passed.")


if __name__ == "__main__":
    main()
