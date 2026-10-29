"""The gold-set scorer with the fake LLM: no cost."""

import json
from pathlib import Path

from adaa.evals.review_gold import GoldReview, load_gold, render, run_gold, save
from adaa.llm.adapters.fake import FakeAdapter

GOLD = [
    GoldReview(
        id="g1", review_id="r1", order_id="o1", text_pt="Chegou quebrado e atrasou",
        meaning="Arrived broken and late", delivery="late",
        product=["defective"], service=["not_mentioned"],
        price="not_mentioned", tone="negative",
    ),
    GoldReview(
        id="g2", review_id="r2", order_id="o2", text_pt="Ótimo produto, chegou rápido",
        meaning="Great product, arrived fast", delivery="on_time", product=["good"],
        service=["not_mentioned"], price="not_mentioned", tone="positive", note="easy",
    ),
]  # fmt: skip


def reply(review: GoldReview, **changes: object) -> str:
    tags = {h: getattr(review, h) for h in ("delivery", "product", "service", "price", "tone")}
    return json.dumps({"text_en": review.meaning} | tags | changes)


def test_all_right_passes() -> None:
    run = run_gold(GOLD, FakeAdapter([reply(g) for g in GOLD]))
    assert run.passed and run.all_right == 2 and run.failed_calls == 0
    assert run.scores["product"].precision == 1.0 and run.scores["tone"].same == 1.0


def test_a_wrong_tag_lowers_its_heading_only() -> None:
    fake = FakeAdapter([reply(GOLD[0], product=["defective", "wrong_or_missing"]),
                        reply(GOLD[1])])  # fmt: skip
    run = run_gold(GOLD, fake)
    product = run.scores["product"]
    assert product.same == 0.5 and product.recall == 1.0  # found every gold tag
    assert product.precision == round(2 / 3, 3)  # but added one gold does not have
    assert run.scores["delivery"].passed and not run.passed
    assert run.results[0].wrong == ["product"]


def test_a_failed_call_is_wrong_everywhere() -> None:
    bad = reply(GOLD[0], delivery="slow")  # not an allowed value: retried once, then fails
    fake = FakeAdapter([bad, bad, reply(GOLD[1])])
    run = run_gold(GOLD, fake)
    assert run.failed_calls == 1 and run.results[0].haiku is None
    assert len(run.results[0].wrong) == 5 and run.scores["tone"].same == 0.5


def test_report_shows_disagreements(tmp_path: Path) -> None:
    run = run_gold(GOLD, FakeAdapter([reply(GOLD[0], tone="mixed"), reply(GOLD[1])]))
    text = render(run)
    assert "**NOT YET**" in text and "## Disagreements (1)" in text
    assert "- **tone**: gold `negative` · Haiku `mixed`" in text and "### g2" not in text
    path = save(run, tmp_path)
    assert path.with_suffix(".md").read_text(encoding="utf-8").startswith("# Review tags")


def test_the_real_gold_file_loads() -> None:
    gold = load_gold()
    assert len(gold) == 100 and len({g.id for g in gold}) == 100
