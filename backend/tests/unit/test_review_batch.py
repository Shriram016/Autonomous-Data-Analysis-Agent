"""Sending the reviews as one batch, with a fake Anthropic client: no cost, no database."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from adaa.ingestion import review_batch
from adaa.ingestion.review_batch import (
    BatchFile,
    Collected,
    collect,
    load_batch,
    open_batches,
    send,
    write,
)
from adaa.ingestion.review_translate import ReviewTranslation, load_review_prompt
from adaa.ingestion.reviews import PendingReview, ReviewRow
from adaa.llm.adapters.anthropic_adapter import AnthropicAdapter, request_params
from adaa.llm.adapters.base import Message
from adaa.llm.config import get_config

REVIEWS = [
    PendingReview("a" * 32, "b" * 32, "Chegou quebrado"),
    PendingReview("c" * 32, "d" * 32, "Ótimo"),
    PendingReview("e" * 32, "f" * 32, "Não recebi"),
]


class FakeBatches:
    def __init__(self, status: str = "ended", entries: list[Any] | None = None) -> None:
        self.sent: list[list[dict[str, Any]]] = []
        self.status, self.entries = status, entries or []

    def create(self, requests: list[dict[str, Any]]) -> SimpleNamespace:
        self.sent.append(requests)
        return SimpleNamespace(id="msgbatch_test")

    def retrieve(self, batch_id: str) -> SimpleNamespace:
        return SimpleNamespace(processing_status=self.status)

    def results(self, batch_id: str) -> list[Any]:
        return self.entries


def fake_adapter(batches: FakeBatches | None = None) -> tuple[AnthropicAdapter, FakeBatches]:
    batches = batches or FakeBatches()
    client = SimpleNamespace(messages=SimpleNamespace(batches=batches))
    return AnthropicAdapter(client=client), batches


@pytest.fixture(autouse=True)
def pending_reviews(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(review_batch, "pending", lambda conn, version: list(REVIEWS))


def test_one_request_per_review_and_the_file_maps_each_id_back(tmp_path: Path) -> None:
    adapter, batches = fake_adapter()
    batch = send(None, adapter=adapter, folder=tmp_path)  # type: ignore[arg-type]
    assert batch is not None and batch.batch_id == "msgbatch_test"
    sent = batches.sent[0]
    assert [r["custom_id"] for r in sent] == ["r00001", "r00002", "r00003"]
    assert all(len(r["custom_id"]) <= 64 for r in sent)

    saved = BatchFile.model_validate_json((tmp_path / f"{batch.name}.json").read_text("utf-8"))
    assert saved.reviews["r00002"].review_id == "c" * 32 and not saved.collected
    assert saved.prompt_version == load_review_prompt().version


def test_a_batch_request_is_the_same_as_a_normal_call(tmp_path: Path) -> None:
    adapter, batches = fake_adapter()
    send(None, adapter=adapter, folder=tmp_path)  # type: ignore[arg-type]
    prompt = load_review_prompt()
    messages = [
        Message(role="system", content=prompt.text),
        Message(role="user", content="Chegou quebrado"),
    ]
    job = get_config().job_settings("review_translate")
    normal = request_params(messages, ReviewTranslation.model_json_schema(), job)
    assert batches.sent[0][0]["params"] == normal


def test_limit_sends_only_the_first_reviews(tmp_path: Path) -> None:
    adapter, batches = fake_adapter()
    send(None, limit=2, adapter=adapter, folder=tmp_path)  # type: ignore[arg-type]
    assert len(batches.sent[0]) == 2


def test_a_dry_run_sends_and_saves_nothing(tmp_path: Path) -> None:
    adapter, batches = fake_adapter()
    assert send(None, dry_run=True, adapter=adapter, folder=tmp_path) is None  # type: ignore[arg-type]
    assert batches.sent == [] and list(tmp_path.iterdir()) == []


def test_an_open_batch_blocks_a_second_send(tmp_path: Path) -> None:
    adapter, batches = fake_adapter()
    batch = send(None, adapter=adapter, folder=tmp_path)  # type: ignore[arg-type]
    assert batch is not None and open_batches(tmp_path) == [batch.name]
    with pytest.raises(RuntimeError, match="collect these batches first"):
        send(None, adapter=adapter, folder=tmp_path)  # type: ignore[arg-type]
    assert len(batches.sent) == 1  # nothing paid twice


def answered(custom_id: str, text: str, stop_reason: str = "end_turn") -> SimpleNamespace:
    """A succeeded batch entry, shaped like the SDK's."""
    usage = SimpleNamespace(input_tokens=300, output_tokens=20)
    message = SimpleNamespace(
        stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)], usage=usage
    )
    return SimpleNamespace(
        custom_id=custom_id, result=SimpleNamespace(type="succeeded", message=message)
    )


def sent_batch(
    tmp_path: Path, entries: list[Any], status: str = "ended"
) -> tuple[AnthropicAdapter, str]:
    """A sent batch with these answers waiting: the adapter and the batch file's name."""
    adapter, _ = fake_adapter(FakeBatches(status, entries))
    batch = send(None, adapter=adapter, folder=tmp_path)  # type: ignore[arg-type]
    assert batch is not None
    return adapter, batch.name


def collected_from(tmp_path: Path, entries: list[Any]) -> Collected:
    adapter, name = sent_batch(tmp_path, entries)
    collected = collect(name, adapter=adapter, folder=tmp_path)
    assert collected is not None
    return collected


def test_collect_keeps_good_answers_and_says_why_others_failed(tmp_path: Path) -> None:
    entries = [
        answered("r00001", '{"text_en": "It arrived broken"}'),
        answered("r00002", "not json"),
        SimpleNamespace(custom_id="r00003", result=SimpleNamespace(type="expired")),
    ]
    collected = collected_from(tmp_path, entries)
    assert [(g.review.review_id, g.text_en) for g in collected.good] == [
        ("a" * 32, "It arrived broken")
    ]
    assert {f.custom_id: f.reason for f in collected.failed} == {
        "r00002": "does not fit the schema",
        "r00003": "request expired",
    }
    # 2 billed answers × (300 in × $0.10 + 20 out × $0.50) / 1M, at half price
    assert collected.cost_usd == pytest.approx(2 * (300 * 0.10 + 20 * 0.50) / 1e6 * 0.5)


def test_collect_checks_the_translation(tmp_path: Path) -> None:
    entries = [
        answered("r00001", '{"text_en": "Chegou quebrado, não recebi o produto"}'),
        answered("r00002", '{"text_en": "Great"}'),
        answered("r00003", '{"text_en": "I did not rec', stop_reason="max_tokens"),
    ]
    collected = collected_from(tmp_path, entries)
    assert [g.text_en for g in collected.good] == ["Great"]
    reasons = {f.custom_id: f.reason for f in collected.failed}
    assert reasons["r00001"].startswith("still Portuguese")
    assert "cut off" in reasons["r00003"]


def test_collect_waits_while_the_batch_is_running(tmp_path: Path) -> None:
    adapter, name = sent_batch(tmp_path, [], status="in_progress")
    assert collect(name, adapter=adapter, folder=tmp_path) is None
    assert not list(tmp_path.glob("*.results.jsonl"))  # nothing to save yet


class FakeEmbedder:
    def embed(self, documents: list[str]) -> list[list[float]]:
        return [[0.1] * 384 for _ in documents]


def test_write_upserts_complete_rows_in_groups_then_closes_the_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    written: list[list[ReviewRow]] = []
    monkeypatch.setattr(review_batch, "upsert", lambda conn, rows: written.append(rows))
    monkeypatch.setattr(review_batch, "GROUP", 2)
    entries = [answered(f"r0000{n}", f'{{"text_en": "Text {n}"}}') for n in (1, 2, 3)]
    collected = collected_from(tmp_path, entries)
    assert write(None, collected, embedder=FakeEmbedder(), folder=tmp_path) == 3  # type: ignore[arg-type]

    assert [len(group) for group in written] == [2, 1]  # one transaction per group
    row = written[1][0]
    assert (row.review_id, row.text_pt, row.text_en) == ("e" * 32, "Não recebi", "Text 3")
    assert len(row.embedding) == 384 and row.embed_model == "BAAI/bge-small-en-v1.5"
    assert row.version.prompt_version == load_review_prompt().version
    closed = load_batch(collected.batch.name, tmp_path)
    assert closed.collected and closed.written == 3 and closed.failed == 0
    assert open_batches(tmp_path) == []  # a new send is allowed again


def test_a_failed_write_leaves_the_batch_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(conn: object, rows: object) -> None:
        raise RuntimeError("database down")

    monkeypatch.setattr(review_batch, "upsert", broken)
    collected = collected_from(tmp_path, [answered("r00001", '{"text_en": "Text"}')])
    with pytest.raises(RuntimeError):
        write(None, collected, embedder=FakeEmbedder(), folder=tmp_path)  # type: ignore[arg-type]
    assert open_batches(tmp_path) == [collected.batch.name]  # collect again later


def test_the_map_is_saved_before_the_send(tmp_path: Path) -> None:
    class Broken(FakeBatches):
        def create(self, requests: list[dict[str, Any]]) -> SimpleNamespace:
            raise RuntimeError("the network broke after Anthropic took the batch")

    adapter, _ = fake_adapter(Broken())
    with pytest.raises(RuntimeError):
        send(None, adapter=adapter, folder=tmp_path)  # type: ignore[arg-type]
    [name] = open_batches(tmp_path)  # the draft blocks a second send: nothing paid twice
    draft = load_batch(name, tmp_path)
    assert draft.batch_id is None and draft.reviews["r00001"].review_id == "a" * 32
    with pytest.raises(RuntimeError, match="Anthropic console"):
        collect(name, adapter=adapter, folder=tmp_path)


def test_answers_are_saved_at_the_first_download_and_read_from_disk_after(
    tmp_path: Path,
) -> None:
    entries = [
        answered("r00001", '{"text_en": "It arrived broken"}'),
        answered("r00002", "not json"),  # a failed answer is saved too, to look at later
    ]
    adapter, name = sent_batch(tmp_path, entries)
    first = collect(name, adapter=adapter, folder=tmp_path)
    saved = (tmp_path / f"{name}.results.jsonl").read_text("utf-8").splitlines()
    assert len(saved) == 2 and "not json" in saved[1]

    offline, _ = fake_adapter(FakeBatches(status="in_progress"))  # Anthropic not asked again
    again = collect(name, adapter=offline, folder=tmp_path)
    assert first is not None and again is not None
    assert again.good == first.good and again.failed == first.failed
    assert again.cost_usd == pytest.approx(first.cost_usd)
