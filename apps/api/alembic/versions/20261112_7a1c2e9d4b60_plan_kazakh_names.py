"""teaching plan names in Kazakh

Revision ID: 7a1c2e9d4b60
Revises: 6e837767b573
Create Date: 2026-11-12 12:00:00

Adds optional Kazakh name, scope and horizon to teaching plans so the planner header is not shown in Russian on the
Kazakh interface. Existing rows keep NULL and fall back to the Russian text.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '7a1c2e9d4b60'
down_revision: str | Sequence[str] | None = '6e837767b573'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('teaching_plans') as batch:
        batch.add_column(sa.Column('name_kz', sa.String(length=200), nullable=True))
        batch.add_column(sa.Column('scope_kz', sa.String(length=200), nullable=True))
        batch.add_column(sa.Column('horizon_kz', sa.String(length=100), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('teaching_plans') as batch:
        batch.drop_column('horizon_kz')
        batch.drop_column('scope_kz')
        batch.drop_column('name_kz')
