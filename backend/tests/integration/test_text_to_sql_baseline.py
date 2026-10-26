"""The baseline's two database parts on real data (experiment, M2 step 3a). No LLM, no cost."""

import pytest

from adaa.settings import get_settings
from experiments.text_to_sql.baseline import read_columns, run_sql

pytestmark = pytest.mark.integration


def test_the_columns_and_keys_are_read_as_adaa_query() -> None:
    columns = read_columns(get_settings().postgres_conninfo("query"))
    assert ("orders", "order_id", "text", True) in columns
    assert ("orders", "order_status", "text", False) in columns
    assert {table for table, *_ in columns} >= {"orders", "order_items", "customers", "reviews"}


def test_queries_run_read_only_and_a_percent_sign_is_plain_text() -> None:
    conninfo = get_settings().postgres_conninfo("query")
    assert run_sql("SELECT count(*) FROM orders", conninfo) == ([(99441,)], None)
    rows, error = run_sql(
        "SELECT count(*) FROM orders WHERE order_status LIKE 'deliver%'", conninfo
    )
    assert error is None and rows == [(96478,)]
    assert run_sql("SELECT no_such_column FROM orders", conninfo) == ([], "sql_error")
    assert run_sql("SELECT pg_sleep(6)", conninfo) == ([], "timeout")
