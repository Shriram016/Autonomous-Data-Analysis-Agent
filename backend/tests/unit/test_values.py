import pytest

from adaa.agent.values import (
    MAX_VALUES,
    ValueCatalogue,
    ValueNotFoundError,
    build_catalogue,
    check_filters,
)
from adaa.semantic_layer.definitions import load
from adaa.semantic_layer.request import StructuredRequest
from adaa.semantic_layer.runner import QueryResult

CATALOGUE = ValueCatalogue(
    values={
        "product_category": ["bed_bath_table", "electronics", "telephony", "toys"],
        "customer_state": ["MG", "RJ", "SP"],
        "payment_type": ["boleto", "credit_card"],
        "review_score": [1, 2, 3, 4, 5],
    }
)


def form_with(dimension: str, *values: object) -> StructuredRequest:
    return StructuredRequest.model_validate(
        {
            "metric": "revenue",
            "filters": [{"dimension": dimension, "op": "in", "values": list(values)}],
        }
    )


def test_exact_values_pass_without_notes() -> None:
    form, notes = check_filters(form_with("customer_state", "SP", "RJ"), CATALOGUE)
    assert form.filters[0].values == ["SP", "RJ"] and notes == []


@pytest.mark.parametrize(
    ("given", "real"),
    [
        ("toy", "toys"),  # plural
        ("Toys", "toys"),  # case
        ("credit card", "credit_card"),  # space
        ("Bed-Bath-Table", "bed_bath_table"),  # hyphens and case
        ("sp", "SP"),
    ],
)
def test_close_values_are_replaced_and_noted(given: str, real: str) -> None:
    dimension = next(d for d, values in CATALOGUE.values.items() if real in values)
    form, notes = check_filters(form_with(dimension, given), CATALOGUE)
    assert form.filters[0].values == [real]
    assert notes == [f"I read '{given}' as '{real}'."]


def test_same_value_as_text_needs_no_note() -> None:
    form, notes = check_filters(form_with("review_score", "5"), CATALOGUE)
    assert form.filters[0].values == [5] and notes == []


def test_unknown_value_names_the_closest_real_values() -> None:
    with pytest.raises(ValueNotFoundError, match="No product_category called 'electronic stuff'"):
        check_filters(form_with("product_category", "electronic stuff"), CATALOGUE)
    with pytest.raises(ValueNotFoundError, match="Did you mean: telephony"):
        check_filters(form_with("product_category", "telephone"), CATALOGUE)


def test_dimension_not_in_the_catalogue_is_not_checked() -> None:
    form, notes = check_filters(form_with("seller", "3442f8959a84dea7ee197c632cb2df15"), CATALOGUE)
    assert form.filters[0].values == ["3442f8959a84dea7ee197c632cb2df15"] and notes == []


def test_build_catalogue_keeps_small_dimensions_only() -> None:
    def fake_ask(request: StructuredRequest) -> QueryResult:
        rows = MAX_VALUES + 1 if request.dimensions == ["seller"] else 3
        values: list[tuple[object, ...]] = [
            (f"{request.dimensions[0]}_{i}", 1) for i in range(rows)
        ]
        return QueryResult(
            columns=["d", "m"], rows=values, explanation=[], row_count=len(values), elapsed_ms=0
        )

    catalogue = build_catalogue(load(), fake_ask)
    assert "seller" not in catalogue.values  # too many values
    assert "month" not in catalogue.values and "year" not in catalogue.values  # dates
    assert catalogue.values["customer_state"] == [f"customer_state_{i}" for i in range(3)]


# --- state names (value_labels) ---

STATES = ValueCatalogue(
    values={"customer_state": ["PA", "RJ", "SP"]},
    labels={"customer_state": {"PA": "Pará", "RJ": "Rio de Janeiro", "SP": "São Paulo"}},
)


def test_prompt_shows_code_and_name() -> None:
    assert (
        STATES.prompt_text() == "- `customer_state`: PA (Pará), RJ (Rio de Janeiro), SP (São Paulo)"
    )


@pytest.mark.parametrize(
    ("given", "code"),
    [("Pará", "PA"), ("Sao Paulo", "SP"), ("são paulo", "SP"), ("rio de janeiro", "RJ")],
)
def test_state_names_become_codes(given: str, code: str) -> None:
    form, notes = check_filters(form_with("customer_state", given), STATES)
    assert form.filters[0].values == [code]
    assert notes == [f"I read '{given}' as '{code}'."]


def test_paris_is_not_para() -> None:
    with pytest.raises(ValueNotFoundError, match="No customer_state called 'Paris' in the data"):
        check_filters(form_with("customer_state", "Paris"), STATES)


def test_real_layer_labels_both_state_dimensions() -> None:
    dims = load().dimensions
    assert dims["customer_state"].value_labels["PA"] == "Pará"
    assert dims["seller_state"].value_labels == dims["customer_state"].value_labels  # one list
    assert len(dims["customer_state"].value_labels) == 27
