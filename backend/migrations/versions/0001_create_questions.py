"""Create conversation.questions: one row per question (§0 M1.5).

The row is created when a question is submitted (so an unknown id is really unknown), and the
worker fills in the answer and the usage when it finishes (the durable usage record).
"""

from alembic import op

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE conversation.questions (
            id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),  -- hard to guess
            owner            text NOT NULL,              -- 'local-dev' until login (M6)
            question         text NOT NULL,
            state            text NOT NULL DEFAULT 'waiting'
                             CHECK (state IN ('waiting', 'running', 'done', 'failed')),
            answer           jsonb,                      -- the FinishedAnswer, when done
            input_tokens     integer NOT NULL DEFAULT 0, -- the durable usage record
            output_tokens    integer NOT NULL DEFAULT 0,
            thinking_tokens  integer NOT NULL DEFAULT 0,
            cost_usd         numeric(12, 6) NOT NULL DEFAULT 0,
            created_at       timestamptz NOT NULL DEFAULT now(),
            started_at       timestamptz,                -- a worker took it
            finished_at      timestamptz,                -- it ended
            -- Worked out by Postgres from the times, so they can never disagree with them.
            wait_seconds     numeric GENERATED ALWAYS AS
                             (EXTRACT(EPOCH FROM started_at - created_at)) STORED,
            total_seconds    numeric GENERATED ALWAYS AS
                             (EXTRACT(EPOCH FROM finished_at - created_at)) STORED
        )
        """
    )
    # "My latest questions" is the common lookup.
    op.execute(
        "CREATE INDEX questions_owner_created ON conversation.questions (owner, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE conversation.questions")
