"""Drop the tag columns from business.review_vectors (§0 M3, tags dropped 2026-10-29).

Haiku now returns only the translation; the facts most tags repeated are in the tables
(order dates and status, the star score). The table was still empty, so nothing is lost.
"""

from alembic import op

revision = "0003"
down_revision = "0002"

TAGS = ("delivery", "product", "service", "price", "tone", "tag_list_version")


def upgrade() -> None:
    op.execute(
        "ALTER TABLE business.review_vectors " + ", ".join(f"DROP COLUMN {name}" for name in TAGS)
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE business.review_vectors
            ADD COLUMN delivery text,
            ADD COLUMN product text[],
            ADD COLUMN service text[],
            ADD COLUMN price text,
            ADD COLUMN tone text,
            ADD COLUMN tag_list_version text
        """
    )
