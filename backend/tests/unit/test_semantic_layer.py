import shutil
from pathlib import Path

import pytest

from adaa.semantic_layer.definitions import FILES, LAYER_DIR, SemanticLayerError, load


@pytest.fixture
def layer_copy(tmp_path: Path) -> Path:
    """A copy of the real YAML files that a test can break."""
    for name in FILES:
        shutil.copy(LAYER_DIR / name, tmp_path / name)
    return tmp_path


def edit(folder: Path, file: str, old: str, new: str) -> None:
    path = folder / file
    text = path.read_text(encoding="utf-8")
    assert old in text, f"test setup: '{old}' not found in {file}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_real_layer_loads() -> None:
    layer = load()
    assert "revenue" in layer.metrics and "product_category" in layer.dimensions
    assert len(layer.fingerprint) == 64


@pytest.mark.parametrize(
    ("metric", "dimension", "allowed"),
    [
        ("revenue", "product_category", True),  # item metric, item dimension
        ("revenue", "customer_state", True),  # item metric, order dimension (above)
        ("revenue", "payment_type", False),  # item vs payment: siblings → double count
        ("total_paid", "payment_type", True),
        ("total_paid", "product_category", False),  # one payment, several categories
        ("average_review_score", "product_category", False),
        ("late_delivery_rate", "month", True),
    ],
)
def test_grain_rule(metric: str, dimension: str, allowed: bool) -> None:
    assert load().can_use(metric, dimension) is allowed


def test_join_path_reaches_category_through_products() -> None:
    path = load().join_path("order_items", {"category_translation"})
    assert [(j.from_table, j.to_table) for j in path] == [
        ("order_items", "products"),
        ("products", "category_translation"),
    ]


def test_unknown_grain_is_refused(layer_copy: Path) -> None:
    edit(layer_copy, "metrics.yaml", "grain: review", "grain: basket")
    with pytest.raises(SemanticLayerError, match="grain"):
        load(layer_copy)


def test_unknown_table_is_refused(layer_copy: Path) -> None:
    edit(layer_copy, "metrics.yaml", "sum(order_items.price)", "sum(order_lines.price)")
    with pytest.raises(SemanticLayerError, match="order_lines"):
        load(layer_copy)


def test_term_used_twice_is_refused(layer_copy: Path) -> None:
    edit(layer_copy, "metrics.yaml", "[freight, shipping cost", "[revenue, shipping cost")
    with pytest.raises(SemanticLayerError, match="term 'revenue'"):
        load(layer_copy)


def test_missing_shown_in_answer_is_refused(layer_copy: Path) -> None:
    edit(layer_copy, "metrics.yaml", '    shown_in_answer: "Freight = ', '    note: "Freight = ')
    with pytest.raises(SemanticLayerError, match="shown_in_answer"):
        load(layer_copy)


def test_unreachable_table_is_refused(layer_copy: Path) -> None:
    edit(
        layer_copy,
        "joins.yaml",
        "  - { from: orders, to: customers, "
        "condition: orders.customer_id = customers.customer_id }\n",
        "",
    )
    with pytest.raises(SemanticLayerError, match="No join path"):
        load(layer_copy)


def test_version_mismatch_is_refused(layer_copy: Path) -> None:
    edit(layer_copy, "joins.yaml", "version: 0.3.3", "version: 0.4.0")
    with pytest.raises(SemanticLayerError, match="different versions"):
        load(layer_copy)


def test_every_metric_has_a_unit() -> None:
    units = {name: m.unit for name, m in load().metrics.items()}
    assert units["orders"] == "count" and units["average_review_score"] == "score"
    assert units["revenue"] == "BRL" and units["late_delivery_rate"] == "ratio"


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("    unit: score  # an average from 1 to 5\n", ""),  # unit missing
        ("unit: days", "unit: hours"),  # not in the fixed list
    ],
)
def test_missing_or_unknown_unit_is_refused(layer_copy: Path, old: str, new: str) -> None:
    edit(layer_copy, "metrics.yaml", old, new)
    with pytest.raises(SemanticLayerError, match="unit"):
        load(layer_copy)


def test_unknown_dimension_kind_is_refused(layer_copy: Path) -> None:
    edit(layer_copy, "dimensions.yaml", "    kind: time\n", "    kind: calendar\n")
    with pytest.raises(SemanticLayerError, match="kind"):
        load(layer_copy)
