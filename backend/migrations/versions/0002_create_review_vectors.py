"""Create business.review_vectors: one row per review with text (§0 M3 ingestion).

The translation, the tags and the vector are filled by later ingestion steps, so they start
empty. The key is (review_id, order_id): review_id alone repeats (F5). No foreign key to
business.reviews: that table has no key of its own and the Olist reload drops and rebuilds
it (the reload drops only its own tables, so this one stays). Tag values are checked in
Python (the structured-output schema), not here.
"""

from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE business.review_vectors (
            review_id        text NOT NULL,
            order_id         text NOT NULL,
            text_pt          text NOT NULL,     -- title + ". " + message, blank parts left out
            text_en          text,              -- filled by translate + tag
            delivery         text,              -- one value, e.g. 'late'
            product          text[],            -- a list, e.g. {damaged_or_defective}
            service          text[],            -- a list
            price            text,              -- one value
            tone             text,              -- one value
            embedding        vector(384),       -- filled by embed (bge-small-en-v1.5)
            -- Worked out by Postgres from text_en, so keyword search never goes stale.
            search_text      tsvector GENERATED ALWAYS AS
                             (to_tsvector('english', coalesce(text_en, ''))) STORED,
            llm_model        text,              -- what made each row, so old rows can be redone
            prompt_version   text,
            tag_list_version text,
            embed_model      text,
            loaded_at        timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (review_id, order_id)  -- 1 review = 1 row: every write is an upsert
        )
        """
    )
    # Keyword search. The vectors have no index for now: an exact scan of ~43k rows is fast.
    op.execute(
        "CREATE INDEX review_vectors_search_text ON business.review_vectors USING gin (search_text)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE business.review_vectors")
