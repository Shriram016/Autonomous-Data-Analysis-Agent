"""Offline tests for the B2 answer number check (eval/answer_check.py)."""

import pandas as pd
import pytest

from eval.answer_check import check_answer, extract_numbers


def vals(text):
    return [n["value"] for n in extract_numbers(text)]


# ---------------------------------------------------------------- extraction
def test_extract_currency_commas_decimals():
    assert vals("Total sales were $2,297,200.86.") == [2297200.86]


def test_extract_suffixes_and_percent():
    got = extract_numbers("Up 20.4% to $763K, about 1.2 million units")
    assert [n["value"] for n in got] == [20.4, 763000.0, 1200000.0]
    assert got[0]["is_percent"] and got[0]["decimals"] == 1


def test_extract_ignores_ordinals_quarters_and_words():
    assert vals("The 1st and 21st of Q4 in FY2017 for item7") == []


def test_extract_negative_and_trailing_period():
    assert vals("A loss of -5,000.50.") == [-5000.5]


# ---------------------------------------------------------------- supported
def test_exact_match_with_formatting():
    t = pd.DataFrame({"Sales_sum": [2297200.8603]})
    r = check_answer("The total sales across all orders is $2,297,200.86.", "total sales?", t)
    assert r["verdict"] == "pass" and r["supported"] == ["$2,297,200.86"]


def test_rounded_value_passes():
    t = pd.DataFrame({"Quantity_mean": [3.789573744246548]})
    assert check_answer("The average is approximately 4 items.", "avg quantity?", t)["verdict"] == "pass"
    assert check_answer("The average is 3.79 items.", "avg quantity?", t)["verdict"] == "pass"


def test_k_and_million_suffix_pass():
    t = pd.DataFrame({"Sales_sum": [286433.0]})
    assert check_answer("Sales were $286K.", "q", t)["verdict"] == "pass"
    assert check_answer("Sales were $0.29 million.", "q", t)["verdict"] == "pass"


def test_percent_written_from_fraction():
    t = pd.DataFrame({"share": [0.204]})
    assert check_answer("That is 20.4% of the total.", "q", t)["verdict"] == "pass"


def test_year_from_numeric_and_text_cells():
    assert check_answer("The best year was 2017.", "q",
                        pd.DataFrame({"Year": [2017], "Profit_sum": [9.0]}))["verdict"] == "pass"
    assert check_answer("It happened in 2017.", "q",
                        pd.DataFrame({"Order Date": ["2017-03-05"]}))["verdict"] == "pass"


def test_negative_table_value_matches_loss_wording():
    t = pd.DataFrame({"Profit_sum": [-5000.0]})
    assert check_answer("There was a loss of $5,000.", "q", t)["verdict"] == "pass"


# ---------------------------------------------------------------- derived
def test_year_over_year_difference_and_pct_change_are_derived():
    t = pd.DataFrame({"Year": [2016, 2017], "Sales_sum": [609205.598, 733215.0]})
    ans = ("Sales were $609,206 in 2016 and $733,215 in 2017, an increase of "
           "$124,009, or 20.4%.")
    r = check_answer(ans, "Compare sales in 2016 and 2017", t)
    assert r["verdict"] == "pass"
    assert "$124,009" in r["derived"] and "20.4%" in r["derived"]


def test_column_total_and_row_count_are_derived():
    t = pd.DataFrame({"State": ["A", "B", "C"], "Sales_sum": [100.0, 200.0, 300.0]})
    r = check_answer("Across 3 states the total is $600.", "q", t)
    assert r["verdict"] == "pass"


# ---------------------------------------------------------------- unsupported (the point)
def test_q41_style_hallucinated_value_fails():
    t = pd.DataFrame({"Sales_sum": [286433.0]})
    r = check_answer("Total sales were $763K.", "q", t)
    assert r["verdict"] == "fail" and r["unsupported"] == ["$763K"]


def test_one_bad_number_among_good_ones_fails():
    t = pd.DataFrame({"Region": ["West"], "Sales_sum": [725457.82]})
    r = check_answer("West had $725,457.82 in sales, up from $999,999.", "q", t)
    assert r["verdict"] == "fail" and r["unsupported"] == ["$999,999"]


# ---------------------------------------------------------------- excused / n-a
def test_numbers_from_the_question_are_excused():
    t = pd.DataFrame({"State": ["CA"], "Sales_sum": [457687.63]})
    r = check_answer("The top 5 was led by CA with $457,687.63.", "Which are the top 5 states?", t)
    assert r["verdict"] == "pass" and r["excused"] == ["5"]


def test_no_numbers_in_answer():
    r = check_answer("The best category is Technology.", "q", pd.DataFrame({"Category": ["Technology"]}))
    assert r["verdict"] == "no_numbers"


@pytest.mark.parametrize("answer,table,fallback", [
    (None, pd.DataFrame({"a": [1]}), False),
    ("", pd.DataFrame({"a": [1]}), False),
    ("It is 5.", None, False),
    ("It is 5.", pd.DataFrame(), False),
    ("a: 1", pd.DataFrame({"a": [1]}), True),  # deterministic fallback, not an LLM answer
])
def test_not_applicable_cases(answer, table, fallback):
    assert check_answer(answer, "q", table, answer_is_fallback=fallback)["verdict"] == "n/a"


# ---------------------------------------------------------------- refinements from historical data
def test_difference_of_rounded_numbers_in_the_answer_is_derived():
    # LLM wrote 609,206 and 733,215 then computed 733,215 - 609,206 = 124,009
    t = pd.DataFrame({"Year": [2016, 2017], "Sales_sum": [609205.598, 733215.9]})
    r = check_answer("Sales rose from $609,206 to $733,215, an increase of $124,009.", "q", t)
    assert r["verdict"] == "pass" and "$124,009" in r["derived"]


def test_group_rollup_sum_is_derived():
    t = pd.DataFrame({"Region": ["E", "E", "W", "W"], "Mode": ["a", "b", "a", "b"],
                      "Sales_sum": [100.0, 250.0, 300.0, 50.0]})
    assert check_answer("East sold $350 in total.", "q", t)["verdict"] == "pass"


def test_wrong_rollup_is_still_flagged():
    t = pd.DataFrame({"Region": ["E", "E", "W", "W"], "Mode": ["a", "b", "a", "b"],
                      "Sales_sum": [100.0, 250.0, 300.0, 50.0]})
    r = check_answer("East sold $777 in total.", "q", t)
    assert r["verdict"] == "fail" and r["unsupported"] == ["$777"]


def test_think_block_is_ignored_and_unclosed_think_is_not_applicable():
    t = pd.DataFrame({"Sales_sum": [286433.0]})
    closed = "<think>maybe 12345 or 2-3 sentences</think>Sales were $286,433."
    assert check_answer(closed, "q", t)["verdict"] == "pass"
    unclosed = "<think>\nOkay, the value is 286,433. I need 2-3 sentences"
    assert check_answer(unclosed, "q", t)["verdict"] == "n/a"
