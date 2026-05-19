"""Add schedule and notification tables

Revision ID: 003_schedules
Revises: 002_farm_management
Create Date: 2025-01-01 00:00:00
"""

from alembic import op
import sqlalchemy as sa

revision      = '003_schedules'
down_revision = '002_farm_management'
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # Add telegram_chat_id and phone_number to users table
    op.add_column('users', sa.Column('telegram_chat_id', sa.String(100), nullable=True))
    op.add_column('users', sa.Column('phone_number',     sa.String(50),  nullable=True))

    op.create_table(
        'scheduled_events',
        sa.Column('id',                 sa.String(36),  primary_key=True),
        sa.Column('user_id',            sa.String(36),  sa.ForeignKey('users.id'),   nullable=False),
        sa.Column('farm_id',            sa.String(36),  sa.ForeignKey('farms.id'),   nullable=True),
        sa.Column('animal_id',          sa.String(36),  sa.ForeignKey('animals.id'), nullable=True),
        sa.Column('schedule_name',      sa.String(255), nullable=False),
        sa.Column('template_key',       sa.String(100), default=''),
        sa.Column('species',            sa.String(50),  default=''),
        sa.Column('title',              sa.String(500), nullable=False),
        sa.Column('description',        sa.Text(),      default=''),
        sa.Column('event_date',         sa.DateTime(),  nullable=False),
        sa.Column('is_critical',        sa.Boolean(),   default=False, server_default=sa.false()),
        sa.Column('reminder_days',      sa.String(100), default='1,0'),
        sa.Column('notify_channels',    sa.String(100), default='push'),
        sa.Column('status',             sa.String(20),  default='pending'),
        sa.Column('last_notified',      sa.DateTime(),  nullable=True),
        sa.Column('notification_count', sa.Integer(),   default=0),
        sa.Column('completed',          sa.Boolean(),   default=False, server_default=sa.false()),
        sa.Column('completed_at',       sa.DateTime(),  nullable=True),
        sa.Column('completion_notes',   sa.Text(),      default=''),
        sa.Column('created_at',         sa.DateTime(),  nullable=True),
        sa.Column('updated_at',         sa.DateTime(),  nullable=True),
    )
    op.create_index('ix_scheduled_events_user_id',    'scheduled_events', ['user_id'])
    op.create_index('ix_scheduled_events_farm_id',    'scheduled_events', ['farm_id'])
    op.create_index('ix_scheduled_events_event_date', 'scheduled_events', ['event_date'])
    op.create_index('ix_scheduled_events_completed',  'scheduled_events', ['completed'])

    op.create_table(
        'push_tokens',
        sa.Column('id',          sa.String(36),  primary_key=True),
        sa.Column('user_id',     sa.String(36),  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('token',       sa.String(500), nullable=False, unique=True),
        sa.Column('device_name', sa.String(255), default=''),
        sa.Column('platform',    sa.String(20),  default=''),
        sa.Column('is_active',   sa.Boolean(),   default=True, server_default=sa.true()),
        sa.Column('created_at',  sa.DateTime(),  nullable=True),
        sa.Column('last_used',   sa.DateTime(),  nullable=True),
    )
    op.create_index('ix_push_tokens_user_id', 'push_tokens', ['user_id'])

    op.create_table(
        'notification_logs',
        sa.Column('id',        sa.String(36),  primary_key=True),
        sa.Column('event_id',  sa.String(36),  sa.ForeignKey('scheduled_events.id'), nullable=False),
        sa.Column('user_id',   sa.String(36),  sa.ForeignKey('users.id'),            nullable=False),
        sa.Column('channel',   sa.String(20),  nullable=False),
        sa.Column('recipient', sa.String(500), default=''),
        sa.Column('message',   sa.Text(),      default=''),
        sa.Column('success',   sa.Boolean(),   default=True, server_default=sa.true()),
        sa.Column('error',     sa.Text(),      default=''),
        sa.Column('sent_at',   sa.DateTime(),  nullable=True),
    )
    op.create_index('ix_notification_logs_event_id', 'notification_logs', ['event_id'])
    op.create_index('ix_notification_logs_user_id',  'notification_logs', ['user_id'])


def downgrade() -> None:
    op.drop_table('notification_logs')
    op.drop_table('push_tokens')
    op.drop_table('scheduled_events')
    op.drop_column('users', 'telegram_chat_id')
    op.drop_column('users', 'phone_number')