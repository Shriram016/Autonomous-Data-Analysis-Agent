import pytest

from adaa.guardrails.numbers import numbers_in, unknown_numbers

# What step 3 would allow for "Revenue by customer state in 2017", plus the question.
ALLOWED = [
    "SP (São Paulo)",
    "R$ 2,136,258.96",
    "RJ (Rio de Janeiro)",
    "R$ 876,499.71",
    "27",  # rows in the full result
    "20",  # rows shown to the LLM
    "R$ 5,962,902.01",  # the total
    "Revenue by customer state in 2017",  # the question
]


def test_numbers_are_found_in_plain_form() -> None:
    text = "SP led with R$ 2,136,258.96 (18.96%) in 2017-03, then 27 states."
    assert numbers_in(text) == ["2136258.96", "18.96", "2017", "03", "27"]


def test_a_correct_answer_passes() -> None:
    answer = (
        "In 2017, SP led all 27 states with R$ 2,136,258.96, followed by RJ with "
        "R$ 876,499.71. Total revenue was R$ 5,962,902.01."
    )
    assert unknown_numbers(answer, ALLOWED) == []


@pytest.mark.parametrize(
    ("answer", "bad"),
    [
        ("SP made 36% of all revenue.", ["36"]),  # a calculated share
        ("SP led with R$ 2.1 million.", ["2.1"]),  # rounded
        ("SP and RJ together made R$ 3,012,758.67.", ["3012758.67"]),  # added up
        ("SP led with R$ 2,136,258.96, about 2.4 times RJ.", ["2.4"]),  # compared
    ],
)
def test_a_number_not_in_the_data_fails(answer: str, bad: list[str]) -> None:
    assert unknown_numbers(answer, ALLOWED) == bad


def test_a_comma_after_a_number_is_not_part_of_it() -> None:
    assert unknown_numbers("Across 27, SP led.", ALLOWED) == []


def test_digits_inside_allowed_names_do_not_cause_a_false_fail() -> None:
    allowed = ["home_appliances_2", "R$ 1,000.00"]
    assert unknown_numbers("home_appliances_2 made R$ 1,000.00.", allowed) == []


def test_month_values_and_percentages_pass() -> None:
    allowed = ["2016-09", "100.00%", "2018-03", "18.96%"]
    answer = "The highest late rate was 100.00% in 2016-09; 2018-03 had 18.96%."
    assert unknown_numbers(answer, allowed) == []


def test_text_without_numbers_passes() -> None:
    assert unknown_numbers("No data matched the question.", []) == []
