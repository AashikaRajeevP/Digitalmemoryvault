"""password reset and auth version

Revision ID: 7c1a9e4b2f60
Revises: fc35b4ffa9c0
Create Date: 2026-11-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7c1a9e4b2f60'
down_revision = 'fc35b4ffa9c0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'auth_version',
                sa.Integer(),
                nullable=False,
                server_default='1',
            )
        )

    op.create_table(
        'password_resets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('otp_hash', sa.String(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('last_sent_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.uid'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )
    with op.batch_alter_table('password_resets', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_password_resets_email'), ['email'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_password_resets_user_id'), ['user_id'], unique=False
        )


def downgrade():
    with op.batch_alter_table('password_resets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_password_resets_user_id'))
        batch_op.drop_index(batch_op.f('ix_password_resets_email'))

    op.drop_table('password_resets')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('auth_version')
