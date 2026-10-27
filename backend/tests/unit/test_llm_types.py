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


def test_cache_write_costs_more_and_cache_read_costs_less() -> None:
    # The same 3,000-token prompt: 2,900 cached + 100 tokens of question at full price.
    plain = cost_usd(3_000, 300, HAIKU)
    write = cost_usd(100, 300, HAIKU, cache_write_tokens=2_900)
    read = cost_usd(100, 300, HAIKU, cache_read_tokens=2_900)
    assert write == pytest.approx(plain + 2_900 * (0.125 - 0.10) / 1_000_000)
    assert read == pytest.approx(plain - 2_900 * (0.10 - 0.01) / 1_000_000)


def test_one_hour_cache_write_uses_its_own_price() -> None:
    five_min = cost_usd(0, 0, HAIKU, cache_write_tokens=1_000_000, cache="5m")
    one_hour = cost_usd(0, 0, HAIKU, cache_write_tokens=1_000_000, cache="1h")
    assert (five_min, one_hour) == pytest.approx((0.125, 0.20))


def test_cache_tokens_add_up_over_two_attempts() -> None:
    first = make_usage(100, 50, 0, HAIKU, cache_write_tokens=2_900)
    retry = make_usage(150, 50, 0, HAIKU, cache_read_tokens=2_900)
    total = first + retry
    assert (total.cache_write_tokens, total.cache_read_tokens) == (2_900, 2_900)
    assert total.cost_usd == pytest.approx(first.cost_usd + retry.cost_usd)


def test_cache_tokens_without_cache_prices_are_an_error() -> None:
    with pytest.raises(ValueError, match="no cache prices"):
        cost_usd(0, 0, Price(input=1.0, output=2.0), cache_read_tokens=10)
