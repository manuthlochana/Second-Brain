"""Initial migration

Revision ID: 001_initial_migration
Revises: 
Create Date: 2024-05-23 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = '001_initial_migration'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Enable Extensions (Only for Postgres)
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    
    # 2. Create Tables
    
    # Entities
    op.create_table('entities',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_entities_name'), 'entities', ['name'], unique=False)
    op.create_index(op.f('ix_entities_entity_type'), 'entities', ['entity_type'], unique=False)

    # Notes
    # For SQLite compatibility, we need to handle Vector type
    embedding_col = Vector(768)
    if bind.dialect.name != 'postgresql':
        embedding_col = sa.Text() 
        
    op.create_table('notes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding', embedding_col, nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Entity-Notes (Many-to-Many)
    op.create_table('entity_notes',
        sa.Column('entity_id', sa.UUID(), nullable=False),
        sa.Column('note_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ),
        sa.ForeignKeyConstraint(['note_id'], ['notes.id'], ),
        sa.PrimaryKeyConstraint('entity_id', 'note_id')
    )

    # Tasks
    op.create_table('tasks',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=True),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_recurring', sa.Boolean(), nullable=True),
        sa.Column('entity_id', sa.UUID(), nullable=True),
        sa.Column('note_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ),
        sa.ForeignKeyConstraint(['note_id'], ['notes.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tasks_status'), 'tasks', ['status'], unique=False)

    # Relationships (Graph Edges)
    op.create_table('relationships',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('source_id', sa.UUID(), nullable=False),
        sa.Column('target_id', sa.UUID(), nullable=False),
        sa.Column('relation_type', sa.String(), nullable=False),
        sa.Column('strength', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['source_id'], ['entities.id'], ),
        sa.ForeignKeyConstraint(['target_id'], ['entities.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Audit Logs
    op.create_table('audit_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    # Drop tables in reverse order of dependency
    op.drop_table('audit_logs')
    op.drop_table('relationships')
    op.drop_index(op.f('ix_tasks_status'), table_name='tasks')
    op.drop_table('tasks')
    op.drop_table('entity_notes')
    op.drop_table('notes') # Vector extension might prevent drop if dependencies exist, but table drop is usually fine
    op.drop_index(op.f('ix_entities_entity_type'), table_name='entities')
    op.drop_index(op.f('ix_entities_name'), table_name='entities')
    op.drop_table('entities')
    
    # Optional: drop extension
    # op.execute("DROP EXTENSION vector")
