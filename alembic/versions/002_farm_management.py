"""Add farm management tables

Revision ID: 002_farm_management
Revises: 001_initial
Create Date: 2025-01-01 00:00:00
"""

from alembic import op
import sqlalchemy as sa

revision      = '002_farm_management'
down_revision = '001_initial'
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        'farms',
        sa.Column('id',         sa.String(36),  primary_key=True),
        sa.Column('owner_id',   sa.String(36),  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('name',       sa.String(255), nullable=False),
        sa.Column('location',   sa.String(500), default=''),
        sa.Column('notes',      sa.Text(),      default=''),
        sa.Column('created_at', sa.DateTime(),  nullable=True),
        sa.Column('updated_at', sa.DateTime(),  nullable=True),
    )
    op.create_index('ix_farms_owner_id', 'farms', ['owner_id'])

    op.create_table(
        'animals',
        sa.Column('id',         sa.String(36),  primary_key=True),
        sa.Column('farm_id',    sa.String(36),  sa.ForeignKey('farms.id'), nullable=False),
        sa.Column('tag_number', sa.String(100), default=''),
        sa.Column('name',       sa.String(255), default=''),
        sa.Column('species',    sa.String(50),  default='cattle'),
        sa.Column('breed',      sa.String(255), default=''),
        sa.Column('sex',        sa.String(10),  default=''),
        sa.Column('dob',        sa.DateTime(),  nullable=True),
        sa.Column('weight_kg',  sa.Float(),     nullable=True),
        sa.Column('notes',      sa.Text(),      default=''),
        sa.Column('is_active',  sa.Boolean(),   default=True, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(),  nullable=True),
    )
    op.create_index('ix_animals_farm_id',    'animals', ['farm_id'])
    op.create_index('ix_animals_tag_number', 'animals', ['tag_number'])

    op.create_table(
        'treatment_records',
        sa.Column('id',                sa.String(36),  primary_key=True),
        sa.Column('farm_id',           sa.String(36),  sa.ForeignKey('farms.id'),   nullable=False),
        sa.Column('animal_id',         sa.String(36),  sa.ForeignKey('animals.id'), nullable=True),
        sa.Column('recorded_by',       sa.String(36),  sa.ForeignKey('users.id'),   nullable=False),
        sa.Column('treatment_date',    sa.DateTime(),  nullable=True),
        sa.Column('number_of_animals', sa.Integer(),   default=1),
        sa.Column('diagnosis',         sa.Text(),      default=''),
        sa.Column('treatment_given',   sa.Text(),      nullable=False),
        sa.Column('dosage',            sa.String(500), default=''),
        sa.Column('route',             sa.String(100), default=''),
        sa.Column('withdrawal_days',   sa.Integer(),   nullable=True),
        sa.Column('follow_up_date',    sa.DateTime(),  nullable=True),
        sa.Column('follow_up_notes',   sa.Text(),      default=''),
        sa.Column('outcome',           sa.String(50),  default='pending'),
        sa.Column('next_action',       sa.Text(),      default=''),
        sa.Column('audio_transcript',  sa.Text(),      default=''),
        sa.Column('audio_language',    sa.String(10),  default='en'),
        sa.Column('created_at',        sa.DateTime(),  nullable=True),
        sa.Column('updated_at',        sa.DateTime(),  nullable=True),
    )
    op.create_index('ix_treatment_farm_id',   'treatment_records', ['farm_id'])
    op.create_index('ix_treatment_animal_id', 'treatment_records', ['animal_id'])
    op.create_index('ix_treatment_date',      'treatment_records', ['treatment_date'])


def downgrade() -> None:
    op.drop_table('treatment_records')
    op.drop_table('animals')
    op.drop_table('farms')
