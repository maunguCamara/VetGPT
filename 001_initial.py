"""Initial schema — users, query_logs, subscriptions

Revision ID: 001_initial
Revises: 
Create Date: 2025-01-01 00:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id',              sa.String(36),  primary_key=True),
        sa.Column('email',           sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('full_name',       sa.String(255), default=''),
        sa.Column('is_active',       sa.Boolean(),   default=True),
        sa.Column('is_verified',     sa.Boolean(),   default=False),
        sa.Column('tier',            sa.String(20),  default='free'),
        sa.Column('created_at',      sa.DateTime(),  nullable=True),
        sa.Column('last_login',      sa.DateTime(),  nullable=True),
    )

    op.create_table(
        'query_logs',
        sa.Column('id',               sa.Integer(),   primary_key=True, autoincrement=True),
        sa.Column('user_id',          sa.String(36),  sa.ForeignKey('users.id'), nullable=True),
        sa.Column('query_text',       sa.Text(),      nullable=False),
        sa.Column('answer_text',      sa.Text(),      default=''),
        sa.Column('sources_used',     sa.Text(),      default=''),
        sa.Column('chunks_retrieved', sa.Integer(),   default=0),
        sa.Column('top_score',        sa.Float(),     default=0.0),
        sa.Column('llm_model',        sa.String(100), default=''),
        sa.Column('latency_ms',       sa.Integer(),   default=0),
        sa.Column('status',           sa.String(20),  default='success'),
        sa.Column('error_message',    sa.Text(),      default=''),
        sa.Column('is_premium_query', sa.Boolean(),   default=False),
        sa.Column('created_at',       sa.DateTime(),  nullable=True),
    )

    op.create_table(
        'subscriptions',
        sa.Column('id',                 sa.Integer(),   primary_key=True, autoincrement=True),
        sa.Column('user_id',            sa.String(36),  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('stripe_customer_id', sa.String(100), default=''),
        sa.Column('stripe_sub_id',      sa.String(100), default=''),
        sa.Column('tier',               sa.String(20),  default='free'),
        sa.Column('status',             sa.String(50),  default='active'),
        sa.Column('current_period_end', sa.DateTime(),  nullable=True),
        sa.Column('created_at',         sa.DateTime(),  nullable=True),
        sa.Column('updated_at',         sa.DateTime(),  nullable=True),
    )


def downgrade() -> None:
    op.drop_table('subscriptions')
    op.drop_table('query_logs')
    op.drop_table('users')
