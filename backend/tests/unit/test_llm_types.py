import pytest

from adaa.llm.config import Price, load
from adaa.llm.types import cost_usd, make_usage

HAIKU = load().models["claude-haiku-5-5"].price_per_million  # $0.10 in / $0.50 out


def test_cost_of_a_typical_question() -> None:
    # 3,000 in x $0.10/M = $0.0003; 300 out x $0.50/M = $0.00015
    assert cost_usd(3_000, 300, HAIKU) == pytest.approx(0.00045)


def test_thinking_tokens_are_not_counted_twice() -> None:
    # 300 visible + 2,000 thinking = 2,300 billed output tokens
    usage = make_usage(3_000, 2_300, thinking_tokens=2_000, price=HAIKU)
    assert usage.cost_usd == pytest.approx(0.0003 + 2_300 * 0.50 / 1_000_000)
    assert usage.thinking_tokens == 2_000


def test_two_attempts_add_up() -> None:
    price = Price(input=1.0, output=2.0)
    total = make_usage(1_000, 100, 0, price) + make_usage(1_200, 150, 50, price)
    assert (total.input_tokens, total.output_tokens, total.thinking_tokens) == (2_200, 250, 50)
    assert total.cost_usd == pytest.approx(cost_usd(2_200, 250, price))
