"""Review ingestion (§0 M3): translate + embed each review, stored in review_vectors.

Incremental and idempotent: each run takes only the reviews still to do, and every write is
an upsert on (review_id, order_id), so a rerun never adds a row.

Runs as adaa_review_writer. Run from backend/:  uv run python -m adaa.ingestion.reviews
"""

from dataclasses import dataclass

import psycopg


@dataclass(frozen=True)
class TranslationVersion:
    """What makes the translation. A row made by anything else is done again."""

    llm_model: str
    prompt_version: str


@dataclass(frozen=True)
class PendingReview:
    review_id: str
    order_id: str
    text_pt: str  # title + ". " + message, blank parts left out


# A review goes in if it has a non-blank title or message (title-only: "Não recomendo").
# NULLIF turns a blank part into NULL. A title that already ends in . ! ? gets only a space,
# so "Entrega rápida!" + message never becomes "Entrega rápida!. …".
# Spaces, tabs and line breaks: many Olist texts end in a Windows line break.
BLANK = "' ' || chr(9) || chr(13) || chr(10)"
PENDING_SQL = f"""
    WITH r AS (
        SELECT review_id, order_id,
               NULLIF(btrim(review_comment_title, {BLANK}), '') AS title,
               NULLIF(btrim(review_comment_message, {BLANK}), '') AS message
        FROM business.reviews
    )
    SELECT r.review_id, r.order_id,
           CASE WHEN r.title IS NULL THEN r.message
                WHEN r.message IS NULL THEN r.title
                WHEN r.title ~ '[.!?]$' THEN r.title || ' ' || r.message
                ELSE r.title || '. ' || r.message
           END AS text_pt
    FROM r
    LEFT JOIN business.review_vectors AS v USING (review_id, order_id)
    WHERE (r.title IS NOT NULL OR r.message IS NOT NULL)
      AND (v.review_id IS NULL                       -- not in the table yet
           OR v.text_en IS NULL                      -- in, but not translated yet
           OR v.llm_model IS DISTINCT FROM %(llm_model)s
           OR v.prompt_version IS DISTINCT FROM %(prompt_version)s)
    ORDER BY r.review_id, r.order_id                 -- the same order on every run
"""


@dataclass(frozen=True)
class ReviewRow:
    """One finished review: everything a row needs. Only complete rows are written (§0)."""

    review_id: str
    order_id: str
    text_pt: str
    text_en: str
    embedding: list[float]  # 384 numbers (bge-small-en-v1.5)
    version: TranslationVersion
    embed_model: str


# Every column is replaced on a second write, so a rerun leaves exactly one up-to-date row.
UPSERT_SQL = """
    INSERT INTO business.review_vectors (
        review_id, order_id, text_pt, text_en, embedding, llm_model, prompt_version,
        embed_model, loaded_at)
    VALUES (%s, %s, %s, %s, %s::vector, %s, %s, %s, now())
    ON CONFLICT (review_id, order_id) DO UPDATE SET
        text_pt = EXCLUDED.text_pt, text_en = EXCLUDED.text_en,
        embedding = EXCLUDED.embedding, llm_model = EXCLUDED.llm_model,
        prompt_version = EXCLUDED.prompt_version,
        embed_model = EXCLUDED.embed_model, loaded_at = EXCLUDED.loaded_at
"""


def vector_literal(numbers: list[float]) -> str:
    """pgvector reads a vector from text like '[0.1,0.2]', so no extra driver package."""
    return "[" + ",".join(repr(float(n)) for n in numbers) + "]"


def upsert(conn: psycopg.Connection, rows: list[ReviewRow]) -> None:
    """Write a group of finished reviews in one transaction: all of them are saved, or none."""
    params = [
        (
            r.review_id, r.order_id, r.text_pt, r.text_en, vector_literal(r.embedding),
            r.version.llm_model, r.version.prompt_version, r.embed_model,
        )
        for r in rows
    ]  # fmt: skip
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(UPSERT_SQL, params)


def pending(conn: psycopg.Connection, version: TranslationVersion) -> list[PendingReview]:
    """The reviews that still need a translation made by `version`."""
    rows = conn.execute(
        PENDING_SQL,
        {"llm_model": version.llm_model, "prompt_version": version.prompt_version},
    ).fetchall()
    return [PendingReview(*row) for row in rows if says_something(row[2])]


def says_something(text: str) -> bool:
    """False for texts of plain punctuation only (". ." or "."): nothing to translate.

    An emoji counts as saying something ("👍" → "thumbs up"). Postgres classes emoji as
    punctuation, so this check is in Python: a letter, a digit or any non-ASCII sign.
    """
    return any(ch.isalnum() or ord(ch) > 127 for ch in text)
