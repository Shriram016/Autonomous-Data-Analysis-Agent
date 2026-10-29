"""Score the review tags against the gold set (§0 M3): Haiku vs the checked gold tags.

Every gold review goes through tag_one (normal calls: 100 calls finish in minutes; the full
run uses the Batch API with the same request). Scores per heading:
- one-value headings (delivery, price, tone): % the same as gold;
- list headings (product, service): % exactly the same list, plus precision (of the tags
  Haiku gave, how many gold has) and recall (of the gold tags, how many Haiku found),
  counting real tags only (not_mentioned is "no tag").
Pass mark (§0): ≥ 90% on every heading (lists: precision and recall). A review whose call
fails counts as wrong on every heading.

Each run writes eval/results/review_gold_<UTC date-time>.json + a readable .md (failures
first). Costs ~$0.01 for 100 reviews. Run from backend/:  uv run python -m adaa.evals.review_gold
"""

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from adaa.agent.prompts import Prompt
from adaa.evals.run import RUNS_DIR
from adaa.ingestion.review_tags import (
    LISTS,
    TAG_LIST_VERSION,
    ReviewTags,
    check_translation,
    load_review_prompt,
    tag_one,
)
from adaa.llm.adapters.base import Adapter
from adaa.llm.types import LlmError
from adaa.settings import REPO_ROOT

GOLD_FILE = REPO_ROOT / "eval" / "gold" / "review_tags_v3.yaml"
HEADINGS = ("delivery", "product", "service", "price", "tone")
PASS_MARK = 0.90
NM = "not_mentioned"


class GoldReview(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    review_id: str
    order_id: str
    text_pt: str
    meaning: str
    delivery: str
    product: list[str]
    service: list[str]
    price: str
    tone: str
    note: str = ""


class ReviewResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    text_pt: str
    meaning: str  # the gold set's plain English meaning
    note: str
    gold: dict[str, str | list[str]]
    haiku: dict[str, str | list[str]] | None  # None: the call failed
    text_en: str | None
    error: str | None
    check_problems: list[str]  # check_translation on Haiku's answer
    wrong: list[str]  # headings that differ from gold
    cost_usd: float


class HeadingScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    same: float  # share of reviews with exactly the gold value / list
    precision: float | None = None  # lists only
    recall: float | None = None
    passed: bool


class GoldRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    started_at: datetime
    prompt: str  # "review_tag 0.1.0 (<fingerprint>)"
    tag_list_version: str
    total: int
    all_right: int  # reviews right on every heading
    failed_calls: int
    scores: dict[str, HeadingScore]
    passed: bool  # every heading passed
    cost_usd: float
    seconds: float
    results: list[ReviewResult]


def load_gold(path: Path = GOLD_FILE) -> list[GoldReview]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [GoldReview.model_validate(r) for r in data["reviews"]]


def tags_of(item: GoldReview | ReviewTags) -> dict[str, str | list[str]]:
    return {h: getattr(item, h) for h in HEADINGS}


def same(a: str | list[str], b: str | list[str]) -> bool:
    return sorted(a) == sorted(b) if isinstance(a, list) and isinstance(b, list) else a == b


def score(results: list[ReviewResult]) -> dict[str, HeadingScore]:
    out = {}
    n = len(results) or 1
    for h in HEADINGS:
        share = sum(h not in r.wrong for r in results) / n
        if h not in LISTS:
            out[h] = HeadingScore(same=round(share, 3), passed=share >= PASS_MARK)
            continue
        given = hits = expected = 0
        for r in results:
            gold = {t for t in r.gold[h] if t != NM}
            haiku = {t for t in (r.haiku or {}).get(h, []) if t != NM}
            given, expected = given + len(haiku), expected + len(gold)
            hits += len(gold & haiku)
        precision = hits / given if given else 1.0
        recall = hits / expected if expected else 1.0
        out[h] = HeadingScore(
            same=round(share, 3),
            precision=round(precision, 3),
            recall=round(recall, 3),
            passed=precision >= PASS_MARK and recall >= PASS_MARK,
        )
    return out


def run_one(review: GoldReview, prompt: Prompt, adapter: Adapter | None) -> ReviewResult:
    gold = tags_of(review)
    try:
        result = tag_one(review.text_pt, prompt, adapter=adapter)
    except LlmError as e:
        return ReviewResult(
            id=review.id, text_pt=review.text_pt, meaning=review.meaning, note=review.note,
            gold=gold, haiku=None, text_en=None, error=f"{type(e).__name__}: {e}",
            check_problems=[], wrong=list(HEADINGS), cost_usd=0.0,
        )  # fmt: skip
    haiku = tags_of(result.output)
    return ReviewResult(
        id=review.id, text_pt=review.text_pt, meaning=review.meaning, note=review.note,
        gold=gold, haiku=haiku, text_en=result.output.text_en, error=None,
        check_problems=check_translation(review.text_pt, result.output),
        wrong=[h for h in HEADINGS if not same(gold[h], haiku[h])],
        cost_usd=result.usage.cost_usd,
    )  # fmt: skip


def run_gold(gold: list[GoldReview], adapter: Adapter | None = None) -> GoldRun:
    started_at, started = datetime.now(UTC), time.monotonic()
    prompt = load_review_prompt()
    results = [run_one(r, prompt, adapter) for r in gold]
    scores = score(results)
    return GoldRun(
        started_at=started_at,
        prompt=f"{prompt.name} {prompt.version} ({prompt.fingerprint[:12]})",
        tag_list_version=TAG_LIST_VERSION,
        total=len(results),
        all_right=sum(not r.wrong for r in results),
        failed_calls=sum(r.error is not None for r in results),
        scores=scores,
        passed=all(s.passed for s in scores.values()),
        cost_usd=round(sum(r.cost_usd for r in results), 6),
        seconds=round(time.monotonic() - started, 1),
        results=results,
    )


def show(value: str | list[str] | None) -> str:
    return ", ".join(value) if isinstance(value, list) else str(value)


def render(run: GoldRun) -> str:
    verdict = "PASS" if run.passed else "NOT YET"
    lines = [
        f"# Review tags vs gold — {run.started_at:%Y-%m-%d %H:%M} UTC",
        "",
        f"**{verdict}** (pass mark {PASS_MARK:.0%} on every heading) · all 5 right in "
        f"{run.all_right} / {run.total} reviews · failed calls {run.failed_calls} · "
        f"${run.cost_usd:.4f} · {run.seconds:.0f} s · prompt {run.prompt} · tags "
        f"{run.tag_list_version}",
        "",
        "| Heading | Same as gold | Precision | Recall | Pass |",
        "|---|---|---|---|---|",
    ]
    for h, s in run.scores.items():
        p = "—" if s.precision is None else f"{s.precision:.0%}"
        rc = "—" if s.recall is None else f"{s.recall:.0%}"
        lines.append(f"| {h} | {s.same:.0%} | {p} | {rc} | {'✅' if s.passed else '❌'} |")
    wrong = [r for r in run.results if r.wrong or r.check_problems]
    lines += ["", f"## Disagreements ({len(wrong)})", ""]
    for r in wrong:
        lines += [f"### {r.id}", "", f"- 🇧🇷 {' '.join(r.text_pt.split())}"]
        lines += [f"- 🇬🇧 gold meaning: {r.meaning}", f"- 🤖 Haiku: {r.text_en or '—'}"]
        if r.error:
            lines.append(f"- ❗ call failed: {r.error}")
        for h in r.wrong:
            haiku = None if r.haiku is None else r.haiku[h]
            lines.append(f"- **{h}**: gold `{show(r.gold[h])}` · Haiku `{show(haiku)}`")
        if r.check_problems:
            lines.append(f"- ⚠️ checks: {'; '.join(r.check_problems)}")
        if r.note:
            lines.append(f"- 📝 gold note: {r.note}")
        lines.append("")
    return "\n".join(lines)


def save(run: GoldRun, folder: Path = RUNS_DIR) -> Path:
    path = folder / f"review_gold_{run.started_at:%Y-%m-%d_%H%M%S}.json"
    path.write_text(run.model_dump_json(indent=2) + "\n", encoding="utf-8")
    path.with_suffix(".md").write_text(render(run) + "\n", encoding="utf-8")
    return path


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    run = run_gold(load_gold())
    path = save(run)
    print(json.dumps({h: s.model_dump(exclude_none=True) for h, s in run.scores.items()}))
    print(f"{'PASS' if run.passed else 'NOT YET'}  all right {run.all_right}/{run.total}  "
          f"failed {run.failed_calls}  ${run.cost_usd:.4f}  {run.seconds:.0f}s")  # fmt: skip
    print(f"Saved {path.relative_to(REPO_ROOT)} + .md")


if __name__ == "__main__":
    main()
