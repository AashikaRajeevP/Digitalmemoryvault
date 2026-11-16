"""memory photos

Revision ID: a3f9c1d7e2b4
Revises: 7c1a9e4b2f60
Create Date: 2026-11-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3f9c1d7e2b4'
down_revision = '7c1a9e4b2f60'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'memory_photos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('memory_id', sa.Integer(), nullable=False),
        sa.Column('public_id', sa.String(), nullable=False),
        sa.Column('secure_url', sa.String(), nullable=False),
        sa.Column(
            'is_cover', sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            'position', sa.Integer(), nullable=False, server_default='0'
        ),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('image_format', sa.String(), nullable=True),
        sa.Column('bytes', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ['memory_id'], ['memories.mid'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('public_id', name='uq_memory_photos_public_id'),
    )
    with op.batch_alter_table('memory_photos', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_memory_photos_memory_id'), ['memory_id'], unique=False
        )


def downgrade():
    with op.batch_alter_table('memory_photos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_memory_photos_memory_id'))

    op.drop_table('memory_photos')
