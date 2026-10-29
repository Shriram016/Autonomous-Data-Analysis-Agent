"""Translate the pending reviews with Haiku as one Message Batch (§0 M3, the full run).

send: each review is the same request as translate_one (the adapter builds both), at half
the price. Anthropic works on the batch in the background, usually in under an hour.
collect: reads the answers and checks each one (schema + check_translation), then embeds
the good ones and upserts them as complete rows (§0: complete rows only). A failed review
gets no row, so the next send picks it up again.

The file data/batches/<batch id>.json maps each short custom_id back to its review: a
custom_id may have at most 64 characters, and review_id + order_id already have 64.

A batch file that is not collected yet blocks a new send, so the same reviews are never
paid for twice.

Run from backend/:
  uv run python -m adaa.ingestion.review_batch send --dry-run    # count + cost, sends nothing
  uv run python -m adaa.ingestion.review_batch send --limit 20   # a small real batch
  uv run python -m adaa.ingestion.review_batch collect           # every open batch → rows
"""

import argparse
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from pydantic import BaseModel, ValidationError

from adaa.ingestion.embed import EMBED_MODEL, Embedder, embed_reviews
from adaa.ingestion.review_translate import (
    ReviewTranslation,
    check_translation,
    load_review_prompt,
)
from adaa.ingestion.reviews import PendingReview, ReviewRow, TranslationVersion, pending, upsert
from adaa.llm.adapters.anthropic_adapter import AnthropicAdapter, BatchAnswer
from adaa.llm.adapters.base import Message
from adaa.llm.config import get_config
from adaa.settings import REPO_ROOT, get_settings

JOB = "review_translate"
BATCHES_DIR = REPO_ROOT / "data" / "batches"  # git-ignored: it holds review text
# Smoke test 2026-10-29: 20 normal calls cost $0.00065. A batch costs half of that.
COST_PER_REVIEW = 0.00065 / 20 * 0.5
GROUP = 1000  # rows embedded and written per transaction


class BatchReview(BaseModel):
    review_id: str
    order_id: str
    text_pt: str  # kept, so collect can check each translation against its original


class BatchFile(BaseModel):
    batch_id: str
    job: str
    llm_model: str
    prompt_version: str
    sent_at: datetime
    collected: bool = False  # set only after every good answer is written
    written: int | None = None  # rows written / failed reviews / real cost, once collected
    failed: int | None = None
    cost_usd: float | None = None
    reviews: dict[str, BatchReview]  # custom_id → the review


def save_batch(batch: BatchFile, folder: Path = BATCHES_DIR) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{batch.batch_id}.json"
    path.write_text(batch.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def custom_id(n: int) -> str:
    return f"r{n:05d}"


def requests_for(
    reviews: list[PendingReview], system_prompt: str
) -> tuple[list[tuple[str, list[Message]]], dict[str, BatchReview]]:
    """One request per review (system prompt + the review), and the custom_id → review map."""
    requests, by_id = [], {}
    for n, r in enumerate(reviews, start=1):
        cid = custom_id(n)
        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=r.text_pt),
        ]
        requests.append((cid, messages))
        by_id[cid] = BatchReview(review_id=r.review_id, order_id=r.order_id, text_pt=r.text_pt)
    return requests, by_id


def open_batches(folder: Path = BATCHES_DIR) -> list[str]:
    """IDs of the batches that were sent but not collected yet."""
    files = sorted(folder.glob("*.json")) if folder.exists() else []
    found = [BatchFile.model_validate_json(f.read_text(encoding="utf-8")) for f in files]
    return [b.batch_id for b in found if not b.collected]


def send(
    conn: psycopg.Connection,
    *,
    limit: int | None = None,
    dry_run: bool = False,
    adapter: AnthropicAdapter | None = None,
    folder: Path = BATCHES_DIR,
) -> BatchFile | None:
    """Send the pending reviews (the first `limit` of them) as one batch and save its file.

    Returns None for a dry run. Raises RuntimeError when a batch is still open.
    """
    if not dry_run and (still_open := open_batches(folder)):
        raise RuntimeError(f"collect these batches first: {', '.join(still_open)}")
    job = get_config().job_settings(JOB)
    prompt = load_review_prompt()
    version = TranslationVersion(llm_model=job.model_name, prompt_version=prompt.version)
    reviews = pending(conn, version)[:limit]
    print(f"{len(reviews)} reviews to send · estimate ${len(reviews) * COST_PER_REVIEW:.4f}")
    if dry_run or not reviews:
        return None

    requests, by_id = requests_for(reviews, prompt.text)
    schema = ReviewTranslation.model_json_schema()
    batch_id = (adapter or AnthropicAdapter()).create_batch(requests, schema, job)
    batch = BatchFile(
        batch_id=batch_id,
        job=JOB,
        llm_model=job.model_name,
        prompt_version=prompt.version,
        sent_at=datetime.now(UTC),
        reviews=by_id,
    )
    path = save_batch(batch, folder)
    print(f"sent batch {batch_id} · saved {path}")
    return batch


@dataclass(frozen=True)
class Good:
    review: BatchReview
    text_en: str


@dataclass(frozen=True)
class Failed:
    custom_id: str
    review: BatchReview
    reason: str


@dataclass(frozen=True)
class Collected:
    """The checked answers of one ended batch, before anything is written."""

    batch: BatchFile
    good: list[Good]
    failed: list[Failed]  # no row for these: the next send picks them up again
    cost_usd: float


def load_batch(batch_id: str, folder: Path = BATCHES_DIR) -> BatchFile:
    return BatchFile.model_validate_json((folder / f"{batch_id}.json").read_text("utf-8"))


def check_answer(review: BatchReview, answer: BatchAnswer) -> str:
    """The English text of a good answer. Raises ValueError with the reason otherwise.

    The same checks as a normal call: the schema, then check_translation. A batch has no
    retry; a failed review simply goes in the next batch.
    """
    if answer.error or answer.text is None:
        raise ValueError(answer.error or "no text")
    try:
        translation = ReviewTranslation.model_validate_json(answer.text)
    except ValidationError as e:
        raise ValueError("does not fit the schema") from e
    if problems := check_translation(review.text_pt, translation):
        raise ValueError("; ".join(problems))
    return translation.text_en


def collect(
    batch_id: str, *, adapter: AnthropicAdapter | None = None, folder: Path = BATCHES_DIR
) -> Collected | None:
    """Read and check the answers of a batch. None while Anthropic is still working on it."""
    batch = load_batch(batch_id, folder)
    job = get_config().job_settings(batch.job)
    adapter = adapter or AnthropicAdapter()
    if (status := adapter.batch_status(batch_id, job)) != "ended":
        print(f"batch {batch_id} is {status}: try again later")
        return None

    answers = {a.custom_id: a for a in adapter.batch_answers(batch_id, job)}
    good, failed = [], []
    for cid, review in batch.reviews.items():
        answer = answers.get(cid) or BatchAnswer(cid, None, "no answer in the results", None)
        try:
            good.append(Good(review, check_answer(review, answer)))
        except ValueError as e:
            failed.append(Failed(cid, review, str(e)))
    cost = sum(a.usage.cost_usd for a in answers.values() if a.usage)
    print(f"batch {batch_id}: {len(good)} good · {len(failed)} failed · ${cost:.5f}")
    for f in failed:
        print(f"  {f.custom_id} failed: {f.reason}")
    return Collected(batch=batch, good=good, failed=failed, cost_usd=cost)


def write(
    conn: psycopg.Connection,
    collected: Collected,
    *,
    embedder: Embedder | None = None,
    folder: Path = BATCHES_DIR,
) -> int:
    """Embed the good answers and upsert them as complete rows, then close the batch.

    Groups of GROUP rows, one transaction each. A crash leaves the batch open: collect it
    again (the results stay downloadable for 29 days); the upsert never adds a second row.
    """
    batch = collected.batch
    version = TranslationVersion(llm_model=batch.llm_model, prompt_version=batch.prompt_version)
    good = collected.good
    for start in range(0, len(good), GROUP):
        group = good[start : start + GROUP]
        vectors = embed_reviews([g.text_en for g in group], embedder)
        rows = [
            ReviewRow(
                review_id=g.review.review_id,
                order_id=g.review.order_id,
                text_pt=g.review.text_pt,
                text_en=g.text_en,
                embedding=vector,
                version=version,
                embed_model=EMBED_MODEL,
            )
            for g, vector in zip(group, vectors, strict=True)
        ]
        upsert(conn, rows)
        print(f"  wrote {start + len(rows)} / {len(good)}")
    closed = batch.model_copy(
        update={
            "collected": True,
            "written": len(good),
            "failed": len(collected.failed),
            "cost_usd": round(collected.cost_usd, 6),
        }
    )
    save_batch(closed, folder)
    print(f"batch {batch.batch_id} closed: {len(good)} rows written")
    return len(good)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(prog="python -m adaa.ingestion.review_batch")
    commands = parser.add_subparsers(dest="command", required=True)
    send_cmd = commands.add_parser("send", help="send the pending reviews as one batch")
    send_cmd.add_argument("--limit", type=int, help="send only the first N reviews")
    send_cmd.add_argument("--dry-run", action="store_true", help="count and cost only")
    collect_cmd = commands.add_parser("collect", help="check, embed and write the open batches")
    collect_cmd.add_argument("batch_id", nargs="?", help="default: every open batch")
    args = parser.parse_args()
    with psycopg.connect(get_settings().postgres_conninfo("review_writer")) as conn:
        if args.command == "send":
            send(conn, limit=args.limit, dry_run=args.dry_run)
            return
        for batch_id in [args.batch_id] if args.batch_id else open_batches():
            if collected := collect(batch_id):
                write(conn, collected)


if __name__ == "__main__":
    main()
