import json
from datetime import date
from pathlib import Path

import pytest

from adaa.agent.prompts import PROMPTS_DIR, PromptError, load_prompt, semantic_values
from adaa.agent.values import ValueCatalogue
from adaa.semantic_layer.definitions import load

AS_OF = date(2018, 8, 31)
CATALOGUE = ValueCatalogue(values={"customer_state": ["RJ", "SP"], "review_score": [1, 5]})


def write(folder: Path, text: str) -> Path:
    (folder / "test.md").write_text(text, encoding="utf-8")
    return folder


def test_real_agent_prompt_is_filled_from_the_semantic_layer() -> None:
    prompt = load_prompt("agent", semantic_values(load(), CATALOGUE, AS_OF))
    assert prompt.version == "0.1.0" and len(prompt.fingerprint) == 64
    assert "{{" not in prompt.text  # every placeholder filled
    assert "- `revenue` (revenue, sales, turnover, product sales):" in prompt.text
    assert "Today is 2018-08-31." in prompt.text
    assert "Delivered orders only." in prompt.text  # a default
    assert "- `customer_state`: RJ, SP" in prompt.text  # the value catalogue
    assert "version:" not in prompt.text  # the version line is not sent to the model


def test_allowed_dimensions_follow_the_grain_rule() -> None:
    text = load_prompt("agent", semantic_values(load(), CATALOGUE, AS_OF)).text
    revenue = next(line for line in text.splitlines() if line.startswith("- `revenue`"))
    assert "product_category" in revenue and "payment_type" not in revenue  # double count


def test_real_answer_prompt_loads() -> None:
    prompt = load_prompt("answer", {})
    assert prompt.version == "0.1.0" and "Never calculate" in prompt.text


def test_missing_value_is_a_clear_error() -> None:
    with pytest.raises(PromptError, match=r"needs a value for \{\{data_as_of\}\}"):
        load_prompt(
            "agent", {"metrics": "", "dimensions": "", "defaults": "", "values": ""}, PROMPTS_DIR
        )


def test_missing_version_line(tmp_path: Path) -> None:
    with pytest.raises(PromptError, match="must start with a line 'version: x.y.z'"):
        load_prompt("test", {}, write(tmp_path, "## Your job\nHello"))


def test_fingerprint_changes_with_any_edit(tmp_path: Path) -> None:
    first = load_prompt("test", {}, write(tmp_path, "version: 1.0.0\n\nHello.")).fingerprint
    second = load_prompt("test", {}, write(tmp_path, "version: 1.0.0\n\nHello!")).fingerprint
    assert first != second


def test_dollar_and_json_braces_stay_plain_text(tmp_path: Path) -> None:
    example = json.dumps({"metric": "revenue", "period": {"start": "2017-01-01"}})
    text = f"version: 1.0.0\n\nSales of R$ 2,140,312.50 for {{{{who}}}}.\nForm: {example}"
    prompt = load_prompt("test", {"who": "SP"}, write(tmp_path, text))
    assert prompt.text == f"Sales of R$ 2,140,312.50 for SP.\nForm: {example}"
