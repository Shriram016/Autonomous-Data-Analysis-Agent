"""review_vectors + the adaa_review_writer role (needs docker compose up + the migrate job)."""

from dataclasses import replace

import psycopg
import pytest

from adaa.ingestion.reviews import ReviewRow, TranslationVersion, pending, upsert
from adaa.settings import get_settings

pytestmark = pytest.mark.integration

VERSION = TranslationVersion("test-model", "test-prompt")


def as_writer() -> psycopg.Connection:
    return psycopg.connect(get_settings().postgres_conninfo("review_writer"))


def finished(review_id: str, order_id: str, text_pt: str, text_en: str) -> ReviewRow:
    return ReviewRow(
        review_id=review_id,
        order_id=order_id,
        text_pt=text_pt,
        text_en=text_en,
        embedding=[0.5] * 384,
        version=VERSION,
        embed_model="test-embed",
    )


def test_a_second_write_updates_the_row_and_never_adds_one() -> None:
    with as_writer() as conn:  # rolled back at the end: no row is left behind
        first = pending(conn, VERSION)[0]  # a real review, so pending() can be checked
        key = (first.review_id, first.order_id)
        row = finished(*key, first.text_pt, "first translation")
        upsert(conn, [row])
        upsert(conn, [replace(row, text_en="second translation", embed_model="test-embed-2")])

        stored = conn.execute(
            "SELECT count(*), max(text_en), max(embed_model), max(llm_model), "
            "max(vector_dims(embedding)), bool_and(search_text @@ to_tsquery('english', 'second')) "
            "FROM business.review_vectors WHERE review_id = %s AND order_id = %s",
            key,
        ).fetchone()
        assert stored == (1, "second translation", "test-embed-2", "test-model", 384, True)
        assert key not in {(p.review_id, p.order_id) for p in pending(conn, VERSION)}
        conn.rollback()


def test_a_new_version_puts_the_review_back_on_the_list() -> None:
    with as_writer() as conn:
        first = pending(conn, VERSION)[0]
        upsert(conn, [finished(first.review_id, first.order_id, first.text_pt, "done")])
        newer = replace(VERSION, prompt_version="test-prompt-v2")
        assert first in pending(conn, newer)  # made by the old prompt: do it again
        conn.rollback()


def test_the_writer_can_change_nothing_else() -> None:
    with as_writer() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("DELETE FROM business.review_vectors")
    with as_writer() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("UPDATE business.reviews SET review_score = 5")


def test_texts_have_no_blank_edges_and_blank_reviews_are_left_out() -> None:
    with as_writer() as conn:
        texts = [p.text_pt for p in pending(conn, VERSION)]
    assert texts and all(t == t.strip() and t for t in texts)  # no "\r\n" left at the end
