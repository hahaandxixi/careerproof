"""Switch the knowledge-chunk index to 384-dimension semantic embeddings.

knowledge_chunks is a pure derived index (rebuildable from resume sections and
project files via app/scripts/reindex_knowledge.py), so the migration clears it
before changing the pgvector column dimension; vectors from the old hash engine
would be meaningless after a truncation anyway. Existing 1024-dimension rows
cannot survive the dimension change, which is intentional.

"""

import sqlalchemy as sa  # noqa: F401 - kept for alembic autogenerate context

from alembic import op

revision = "0012_knowledge_vec384"
down_revision = "0011_reply_refs"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_knowledge_chunks_embedding_hnsw"


def _reset_to(dimension: int) -> None:
    op.execute("DELETE FROM knowledge_chunks")
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
    op.execute(f"ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector({dimension})")
    op.execute(
        f"CREATE INDEX {INDEX_NAME} ON knowledge_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def upgrade() -> None:
    _reset_to(384)


def downgrade() -> None:
    _reset_to(1024)
