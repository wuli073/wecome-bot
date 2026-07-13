"""add broadcast rules tables

Revision ID: 0013_broadcast_rules
Revises: 0012_desktop_runs
Create Date: 2026-07-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0013_broadcast_rules'
down_revision = '0012_desktop_runs'
branch_labels = None
depends_on = None


def _table_names(inspector) -> set[str]:
    return set(inspector.get_table_names())


def _index_names(inspector, table_name: str) -> set[str]:
    if table_name not in _table_names(inspector):
        return set()
    return {index['name'] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = _table_names(inspector)

    if 'broadcast_templates' not in tables:
        op.create_table(
            'broadcast_templates',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('bot_uuid', sa.String(length=255), nullable=False),
            sa.Column('connector_id', sa.String(length=255), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('variables', sa.JSON(), nullable=False, server_default='[]'),
            sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint(
                'bot_uuid',
                'connector_id',
                'name',
                name='uq_broadcast_templates_scope_name',
            ),
        )

    if 'broadcast_variable_profiles' not in tables:
        op.create_table(
            'broadcast_variable_profiles',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('bot_uuid', sa.String(length=255), nullable=False),
            sa.Column('connector_id', sa.String(length=255), nullable=False),
            sa.Column('group_field', sa.String(length=255), nullable=True),
            sa.Column('mapping_rules', sa.JSON(), nullable=False, server_default='[]'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint(
                'bot_uuid',
                'connector_id',
                name='uq_broadcast_variable_profiles_scope',
            ),
        )

    if 'broadcast_group_rules' not in tables:
        op.create_table(
            'broadcast_group_rules',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('bot_uuid', sa.String(length=255), nullable=False),
            sa.Column('connector_id', sa.String(length=255), nullable=False),
            sa.Column('source_value', sa.String(length=255), nullable=False),
            sa.Column('match_type', sa.String(length=50), nullable=False),
            sa.Column('match_expression', sa.String(length=1024), nullable=False),
            sa.Column('target_conversation_name', sa.String(length=255), nullable=False),
            sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint(
                'bot_uuid',
                'connector_id',
                'source_value',
                'match_type',
                'match_expression',
                'target_conversation_name',
                name='uq_broadcast_group_rules_scope_rule',
            ),
        )

    if 'broadcast_group_names' not in tables:
        op.create_table(
            'broadcast_group_names',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('bot_uuid', sa.String(length=255), nullable=False),
            sa.Column('connector_id', sa.String(length=255), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint(
                'bot_uuid',
                'connector_id',
                'name',
                name='uq_broadcast_group_names_scope_name',
            ),
        )

    inspector = sa.inspect(conn)
    index_specs = [
        ('broadcast_templates', 'ix_broadcast_templates_bot_uuid', ['bot_uuid']),
        ('broadcast_templates', 'ix_broadcast_templates_connector_id', ['connector_id']),
        ('broadcast_templates', 'ix_broadcast_templates_name', ['name']),
        ('broadcast_variable_profiles', 'ix_broadcast_variable_profiles_bot_uuid', ['bot_uuid']),
        ('broadcast_variable_profiles', 'ix_broadcast_variable_profiles_connector_id', ['connector_id']),
        ('broadcast_group_rules', 'ix_broadcast_group_rules_bot_uuid', ['bot_uuid']),
        ('broadcast_group_rules', 'ix_broadcast_group_rules_connector_id', ['connector_id']),
        ('broadcast_group_rules', 'ix_broadcast_group_rules_source_value', ['source_value']),
        ('broadcast_group_rules', 'ix_broadcast_group_rules_match_type', ['match_type']),
        ('broadcast_group_rules', 'ix_broadcast_group_rules_priority', ['priority']),
        ('broadcast_group_names', 'ix_broadcast_group_names_bot_uuid', ['bot_uuid']),
        ('broadcast_group_names', 'ix_broadcast_group_names_connector_id', ['connector_id']),
        ('broadcast_group_names', 'ix_broadcast_group_names_name', ['name']),
    ]
    for table_name, index_name, columns in index_specs:
        if index_name not in _index_names(inspector, table_name):
            op.create_index(index_name, table_name, columns)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = _table_names(inspector)

    drop_specs = {
        'broadcast_group_names': [
            'ix_broadcast_group_names_name',
            'ix_broadcast_group_names_connector_id',
            'ix_broadcast_group_names_bot_uuid',
        ],
        'broadcast_group_rules': [
            'ix_broadcast_group_rules_priority',
            'ix_broadcast_group_rules_match_type',
            'ix_broadcast_group_rules_source_value',
            'ix_broadcast_group_rules_connector_id',
            'ix_broadcast_group_rules_bot_uuid',
        ],
        'broadcast_variable_profiles': [
            'ix_broadcast_variable_profiles_connector_id',
            'ix_broadcast_variable_profiles_bot_uuid',
        ],
        'broadcast_templates': [
            'ix_broadcast_templates_name',
            'ix_broadcast_templates_connector_id',
            'ix_broadcast_templates_bot_uuid',
        ],
    }

    for table_name, index_names in drop_specs.items():
        if table_name not in tables:
            continue
        for index_name in index_names:
            try:
                op.drop_index(index_name, table_name=table_name)
            except Exception:
                pass

    for table_name in [
        'broadcast_group_names',
        'broadcast_group_rules',
        'broadcast_variable_profiles',
        'broadcast_templates',
    ]:
        if table_name in tables:
            op.drop_table(table_name)
