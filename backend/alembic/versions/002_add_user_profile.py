"""Add UserProfile and index Task due_date

Revision ID: 002_add_user_profile
Revises: 001_initial_migration
Create Date: 2024-05-23 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_add_user_profile'
down_revision = '001_initial_migration'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create user_profiles table
    op.create_table('user_profiles',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('bio_memory', sa.JSON(), nullable=True),
        sa.Column('stats', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add index to tasks.due_date
    op.create_index(op.f('ix_tasks_due_date'), 'tasks', ['due_date'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_tasks_due_date'), table_name='tasks')
    op.drop_table('user_profiles')
