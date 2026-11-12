"""initial_schema

Revision ID: 2b566568e9f6
Revises: 
Create Date: 2026-11-09 12:57:34.625115

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2b566568e9f6'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Base Organization & Type Tables
    op.create_table('department_types',
        sa.Column('department_type_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('type_name', sa.String(length=100), nullable=False),
        sa.Column('type_code', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_by', sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint('department_type_id'),
        sa.UniqueConstraint('type_code'),
        sa.UniqueConstraint('type_name')
    )

    op.create_table('departments',
        sa.Column('department_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('department_name', sa.String(length=100), nullable=False),
        sa.Column('department_code', sa.String(length=50), nullable=False),
        sa.Column('department_type_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_by', sa.UUID(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.ForeignKeyConstraint(['department_type_id'], ['department_types.department_type_id'], ),
        sa.PrimaryKeyConstraint('department_id'),
        sa.UniqueConstraint('department_code'),
        sa.UniqueConstraint('department_name')
    )
    op.create_index('idx_departments_department_type_id', 'departments', ['department_type_id'], unique=False)

    op.create_table('designations',
        sa.Column('designation_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('designation_name', sa.String(length=100), nullable=False),
        sa.Column('designation_code', sa.String(length=50), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_by', sa.UUID(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.PrimaryKeyConstraint('designation_id'),
        sa.UniqueConstraint('designation_code'),
        sa.UniqueConstraint('designation_name')
    )
    op.create_index('idx_designations_is_active', 'designations', ['is_active'], unique=False)
    op.create_index('idx_designations_level', 'designations', ['level'], unique=False)

    # 2. Master Status Table (Must precede employees and reviews)
    op.create_table('status_master',
        sa.Column('status_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('status_code', sa.String(length=50), nullable=False),
        sa.Column('status_name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_by', sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint('status_id'),
        sa.UniqueConstraint('status_code')
    )
    op.create_index('idx_status_master_entity_type', 'status_master', ['entity_type'], unique=False)
    op.create_index('idx_status_master_entity_type_status_code', 'status_master', ['entity_type', 'status_code'], unique=False)

    # 3. Roles Table (Must precede employee_roles and route_permissions)
    op.create_table('roles',
        sa.Column('role_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('role_name', sa.String(length=100), nullable=False),
        sa.Column('role_code', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_by', sa.UUID(), nullable=True),
        sa.Column('reviewer_weight', sa.Numeric(precision=5, scale=4), server_default='1.0000', nullable=False),
        sa.PrimaryKeyConstraint('role_id'),
        sa.UniqueConstraint('role_code'),
        sa.UniqueConstraint('role_name')
    )

    # 4. Employees Table (All prerequisite foreign tables now exist)
    op.create_table('employees',
        sa.Column('employee_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('designation_id', sa.UUID(), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('department_id', sa.UUID(), nullable=False),
        sa.Column('manager_id', sa.UUID(), nullable=True),
        sa.Column('date_of_joining', sa.Date(), nullable=False),
        sa.Column('status_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_by', sa.UUID(), nullable=True),
        sa.Column('date_of_birth', sa.Date(), nullable=True),
        sa.Column('must_change_password', sa.Boolean(), server_default='true', nullable=False),
        sa.ForeignKeyConstraint(['department_id'], ['departments.department_id'], ),
        sa.ForeignKeyConstraint(['designation_id'], ['designations.designation_id'], ),
        sa.ForeignKeyConstraint(['manager_id'], ['employees.employee_id'], ),
        sa.ForeignKeyConstraint(['status_id'], ['status_master.status_id'], ),
        sa.PrimaryKeyConstraint('employee_id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('username')
    )
    op.create_index('idx_employees_created_at', 'employees', ['created_at'], unique=False)
    op.create_index('idx_employees_date_of_birth', 'employees', ['date_of_birth'], unique=False)
    op.create_index('idx_employees_date_of_joining', 'employees', ['date_of_joining'], unique=False)
    op.create_index('idx_employees_department_id', 'employees', ['department_id'], unique=False)
    op.create_index('idx_employees_department_id_status_id', 'employees', ['department_id', 'status_id'], unique=False)
    op.create_index('idx_employees_designation_id', 'employees', ['designation_id'], unique=False)
    op.create_index('idx_employees_manager_id', 'employees', ['manager_id'], unique=False)
    op.create_index('idx_employees_manager_id_status_id', 'employees', ['manager_id', 'status_id'], unique=False)
    op.create_index('idx_employees_status_id', 'employees', ['status_id'], unique=False)

    # 5. Core Operational Tables
    op.create_table('notifications',
        sa.Column('notification_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('employee_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('is_read', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('email_sent', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('send_attempts', sa.Integer(), server_default='0', nullable=False),
        sa.PrimaryKeyConstraint('notification_id')
    )
    op.create_index('idx_notifications_created_at', 'notifications', ['created_at'], unique=False)
    op.create_index('idx_notifications_email_sent_type_send_created', 'notifications', ['email_sent', 'type', 'send_attempts', 'created_at'], unique=False)
    op.create_index('idx_notifications_employee_id', 'notifications', ['employee_id'], unique=False)
    op.create_index('idx_notifications_employee_id_is_read', 'notifications', ['employee_id', 'is_read'], unique=False)

    op.create_table('audit_log',
        sa.Column('audit_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('table_name', sa.String(length=100), nullable=False),
        sa.Column('record_id', sa.UUID(), nullable=False),
        sa.Column('operation_type', sa.String(length=50), nullable=False),
        sa.Column('old_values', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('new_values', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('performed_by', sa.UUID(), nullable=False),
        sa.Column('performed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['performed_by'], ['employees.employee_id'], ),
        sa.PrimaryKeyConstraint('audit_id')
    )
    op.create_index('idx_audit_log_operation_type', 'audit_log', ['operation_type'], unique=False)
    op.create_index('idx_audit_log_performed_at', 'audit_log', ['performed_at'], unique=False)
    op.create_index('idx_audit_log_performed_by', 'audit_log', ['performed_by'], unique=False)
    op.create_index('idx_audit_log_record_id', 'audit_log', ['record_id'], unique=False)
    op.create_index('idx_audit_log_table_name', 'audit_log', ['table_name'], unique=False)
    op.create_index('idx_audit_log_table_record', 'audit_log', ['table_name', 'record_id'], unique=False)
    op.create_index('idx_audit_log_table_record_performed', 'audit_log', ['table_name', 'record_id', 'performed_at'], unique=False)

    op.create_table('refresh_tokens',
        sa.Column('token_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('employee_id', sa.UUID(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('replaced_by_token', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.employee_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('token_id'),
        sa.UniqueConstraint('token_hash')
    )
    op.create_index('idx_refresh_tokens_employee_id', 'refresh_tokens', ['employee_id'], unique=False)
    op.create_index('idx_refresh_tokens_token_hash', 'refresh_tokens', ['token_hash'], unique=False)

    # 6. Recognition & Review Tables
    op.create_table('review_categories',
        sa.Column('category_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('category_code', sa.String(length=50), nullable=False),
        sa.Column('category_name', sa.String(length=100), nullable=False),
        sa.Column('multiplier', sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_by', sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint('category_id'),
        sa.UniqueConstraint('category_code'),
        sa.UniqueConstraint('category_name')
    )
    op.create_index('idx_review_categories_category_code', 'review_categories', ['category_code'], unique=False)
    op.create_index('idx_review_categories_is_active', 'review_categories', ['is_active'], unique=False)

    op.create_table('reviews',
        sa.Column('review_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('reviewer_id', sa.UUID(), nullable=False),
        sa.Column('receiver_id', sa.UUID(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=False),
        sa.Column('image_url', sa.String(length=500), nullable=True),
        sa.Column('video_url', sa.String(length=500), nullable=True),
        sa.Column('status_id', sa.UUID(), nullable=False),
        sa.Column('review_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_by', sa.UUID(), nullable=False),
        sa.Column('raw_points', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['employees.employee_id'], ),
        sa.ForeignKeyConstraint(['receiver_id'], ['employees.employee_id'], ),
        sa.ForeignKeyConstraint(['reviewer_id'], ['employees.employee_id'], ),
        sa.ForeignKeyConstraint(['status_id'], ['status_master.status_id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['employees.employee_id'], ),
        sa.PrimaryKeyConstraint('review_id')
    )
    op.create_index('idx_reviews_receiver_id', 'reviews', ['receiver_id'], unique=False)
    op.create_index('idx_reviews_receiver_raw_points', 'reviews', ['receiver_id', 'raw_points'], unique=False)
    op.create_index('idx_reviews_receiver_review_at', 'reviews', ['receiver_id', 'review_at'], unique=False)
    op.create_index('idx_reviews_receiver_status_id', 'reviews', ['receiver_id', 'status_id'], unique=False)
    op.create_index('idx_reviews_review_at', 'reviews', ['review_at'], unique=False)
    op.create_index('idx_reviews_reviewer_id', 'reviews', ['reviewer_id'], unique=False)
    op.create_index('idx_reviews_reviewer_review_at', 'reviews', ['reviewer_id', 'review_at'], unique=False)
    op.create_index('idx_reviews_status_id', 'reviews', ['status_id'], unique=False)

    op.create_table('review_category_tags',
        sa.Column('tag_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('review_id', sa.UUID(), nullable=False),
        sa.Column('category_id', sa.UUID(), nullable=False),
        sa.Column('multiplier_snapshot', sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column('category_code_snapshot', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['review_categories.category_id'], ),
        sa.ForeignKeyConstraint(['review_id'], ['reviews.review_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('tag_id'),
        sa.UniqueConstraint('review_id', 'category_id', name='uq_review_category_tags_review_category')
    )
    op.create_index('idx_review_category_tags_category_id', 'review_category_tags', ['category_id'], unique=False)
    op.create_index('idx_review_category_tags_review_id', 'review_category_tags', ['review_id'], unique=False)

    # 7. Rewards, Wallets & Financial Tables
    op.create_table('reward_categories',
        sa.Column('category_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('category_name', sa.String(length=100), nullable=False),
        sa.Column('category_code', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_by', sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint('category_id'),
        sa.UniqueConstraint('category_code'),
        sa.UniqueConstraint('category_name')
    )
    op.create_index('idx_reward_categories_is_active', 'reward_categories', ['is_active'], unique=False)

    op.create_table('reward_catalog',
        sa.Column('catalog_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('reward_name', sa.String(length=200), nullable=False),
        sa.Column('reward_code', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('default_points', sa.Integer(), nullable=False),
        sa.Column('category_id', sa.UUID(), nullable=False),
        sa.Column('min_points', sa.Integer(), nullable=False),
        sa.Column('max_points', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_by', sa.UUID(), nullable=True),
        sa.Column('available_stock', sa.Integer(), server_default='0', nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['reward_categories.category_id'], ),
        sa.PrimaryKeyConstraint('catalog_id'),
        sa.UniqueConstraint('reward_code'),
        sa.UniqueConstraint('reward_name')
    )
    op.create_index('idx_reward_catalog_category_id', 'reward_catalog', ['category_id'], unique=False)
    op.create_index('idx_reward_catalog_category_is_active', 'reward_catalog', ['category_id', 'is_active'], unique=False)
    op.create_index('idx_reward_catalog_is_active', 'reward_catalog', ['is_active'], unique=False)
    op.create_index('idx_reward_catalog_min_max_points', 'reward_catalog', ['min_points', 'max_points'], unique=False)

    op.create_table('transaction_types',
        sa.Column('type_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('type_name', sa.String(length=100), nullable=False),
        sa.Column('type_code', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_credit', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_by', sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint('type_id'),
        sa.UniqueConstraint('type_code'),
        sa.UniqueConstraint('type_name')
    )
    op.create_index('idx_transaction_types_is_credit', 'transaction_types', ['is_credit'], unique=False)

    op.create_table('wallets',
        sa.Column('wallet_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('employee_id', sa.UUID(), nullable=False),
        sa.Column('available_points', sa.Integer(), server_default='0', nullable=False),
        sa.Column('redeemed_points', sa.Integer(), server_default='0', nullable=False),
        sa.Column('total_earned_points', sa.Integer(), server_default='0', nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_by', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['employees.employee_id'], ),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.employee_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by'], ['employees.employee_id'], ),
        sa.PrimaryKeyConstraint('wallet_id'),
        sa.UniqueConstraint('employee_id')
    )
    op.create_index('idx_wallets_available_points', 'wallets', ['available_points'], unique=False)
    op.create_index('idx_wallets_total_earned_points', 'wallets', ['total_earned_points'], unique=False)

    op.create_table('transactions',
        sa.Column('transaction_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('wallet_id', sa.UUID(), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('transaction_type_id', sa.UUID(), nullable=False),
        sa.Column('status_id', sa.UUID(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('reference_number', sa.String(length=100), nullable=False),
        sa.Column('transaction_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_by', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['employees.employee_id'], ),
        sa.ForeignKeyConstraint(['status_id'], ['status_master.status_id'], ),
        sa.ForeignKeyConstraint(['transaction_type_id'], ['transaction_types.type_id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['employees.employee_id'], ),
        sa.ForeignKeyConstraint(['wallet_id'], ['wallets.wallet_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('transaction_id'),
        sa.UniqueConstraint('reference_number')
    )
    op.create_index('idx_transactions_created_at', 'transactions', ['created_at'], unique=False)
    op.create_index('idx_transactions_status_id', 'transactions', ['status_id'], unique=False)
    op.create_index('idx_transactions_transaction_at', 'transactions', ['transaction_at'], unique=False)
    op.create_index('idx_transactions_transaction_type_id', 'transactions', ['transaction_type_id'], unique=False)
    op.create_index('idx_transactions_wallet_id', 'transactions', ['wallet_id'], unique=False)
    op.create_index('idx_transactions_wallet_status', 'transactions', ['wallet_id', 'status_id'], unique=False)
    op.create_index('idx_transactions_wallet_transaction_at', 'transactions', ['wallet_id', 'transaction_at'], unique=False)

    op.create_table('reward_history',
        sa.Column('history_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('wallet_id', sa.UUID(), nullable=False),
        sa.Column('catalog_id', sa.UUID(), nullable=False),
        sa.Column('granted_by', sa.UUID(), nullable=False),
        sa.Column('points', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('granted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_by', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['catalog_id'], ['reward_catalog.catalog_id'], ),
        sa.ForeignKeyConstraint(['created_by'], ['employees.employee_id'], ),
        sa.ForeignKeyConstraint(['granted_by'], ['employees.employee_id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['employees.employee_id'], ),
        sa.ForeignKeyConstraint(['wallet_id'], ['wallets.wallet_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('history_id')
    )
    op.create_index('idx_reward_history_catalog_granted', 'reward_history', ['catalog_id', 'granted_at'], unique=False)
    op.create_index('idx_reward_history_catalog_id', 'reward_history', ['catalog_id'], unique=False)
    op.create_index('idx_reward_history_granted_at', 'reward_history', ['granted_at'], unique=False)
    op.create_index('idx_reward_history_granted_by', 'reward_history', ['granted_by'], unique=False)
    op.create_index('idx_reward_history_wallet_granted', 'reward_history', ['wallet_id', 'granted_at'], unique=False)
    op.create_index('idx_reward_history_wallet_id', 'reward_history', ['wallet_id'], unique=False)

    # 8. Dependent Role & Permission Tables
    op.create_table('employee_roles',
        sa.Column('employee_role_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('employee_id', sa.UUID(), nullable=False),
        sa.Column('role_id', sa.UUID(), nullable=False),
        sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('assigned_by', sa.UUID(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_by', sa.UUID(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_by', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['assigned_by'], ['employees.employee_id'], ),
        sa.ForeignKeyConstraint(['created_by'], ['employees.employee_id'], ),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.employee_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['revoked_by'], ['employees.employee_id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.role_id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['employees.employee_id'], ),
        sa.PrimaryKeyConstraint('employee_role_id'),
        sa.UniqueConstraint('employee_id', 'role_id', 'is_active', name='uq_employee_role_active')
    )
    op.create_index('idx_employee_roles_assigned_at', 'employee_roles', ['assigned_at'], unique=False)
    op.create_index('idx_employee_roles_employee_id', 'employee_roles', ['employee_id'], unique=False)
    op.create_index('idx_employee_roles_employee_id_is_active', 'employee_roles', ['employee_id', 'is_active'], unique=False)
    op.create_index('idx_employee_roles_is_active', 'employee_roles', ['is_active'], unique=False)
    op.create_index('idx_employee_roles_revoked_at', 'employee_roles', ['revoked_at'], unique=False)
    op.create_index('idx_employee_roles_role_id', 'employee_roles', ['role_id'], unique=False)

    op.create_table('route_permissions',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('route_key', sa.String(length=200), nullable=False),
        sa.Column('role_id', sa.UUID(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', sa.UUID(), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(['role_id'], ['roles.role_id'], name='fk_route_permissions_role', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('route_key', 'role_id', name='uq_route_permissions_route_role')
    )
    op.create_index('idx_route_permissions_route_key', 'route_permissions', ['route_key'], unique=False)

    # 9. Circular Foreign Keys to employees (Applied last)
    op.create_foreign_key(
        'fk_department_types_created_by', 'department_types', 'employees',
        ['created_by'], ['employee_id'], ondelete='RESTRICT'
    )
    op.create_foreign_key(
        'fk_department_types_updated_by', 'department_types', 'employees',
        ['updated_by'], ['employee_id'], ondelete='RESTRICT'
    )
    op.create_foreign_key(
        'fk_departments_created_by', 'departments', 'employees',
        ['created_by'], ['employee_id'], ondelete='RESTRICT'
    )
    op.create_foreign_key(
        'fk_departments_updated_by', 'departments', 'employees',
        ['updated_by'], ['employee_id'], ondelete='RESTRICT'
    )
    op.create_foreign_key(
        'fk_designations_created_by', 'designations', 'employees',
        ['created_by'], ['employee_id'], ondelete='RESTRICT'
    )
    op.create_foreign_key(
        'fk_designations_updated_by', 'designations', 'employees',
        ['updated_by'], ['employee_id'], ondelete='RESTRICT'
    )
    op.create_foreign_key(
        'fk_status_master_created_by', 'status_master', 'employees',
        ['created_by'], ['employee_id'], ondelete='RESTRICT'
    )
    op.create_foreign_key(
        'fk_status_master_updated_by', 'status_master', 'employees',
        ['updated_by'], ['employee_id'], ondelete='RESTRICT'
    )
    op.create_foreign_key(
        'fk_roles_created_by', 'roles', 'employees',
        ['created_by'], ['employee_id'], ondelete='RESTRICT'
    )
    op.create_foreign_key(
        'fk_roles_updated_by', 'roles', 'employees',
        ['updated_by'], ['employee_id'], ondelete='RESTRICT'
    )
    op.create_foreign_key(
        'fk_employees_created_by', 'employees', 'employees',
        ['created_by'], ['employee_id'], ondelete='RESTRICT'
    )
    op.create_foreign_key(
        'fk_employees_updated_by', 'employees', 'employees',
        ['updated_by'], ['employee_id'], ondelete='RESTRICT'
    )
    op.create_foreign_key(
        'fk_review_categories_created_by', 'review_categories', 'employees',
        ['created_by'], ['employee_id'], ondelete='RESTRICT'
    )
    op.create_foreign_key(
        'fk_review_categories_updated_by', 'review_categories', 'employees',
        ['updated_by'], ['employee_id'], ondelete='RESTRICT'
    )
    op.create_foreign_key(
        'fk_reward_categories_created_by', 'reward_categories', 'employees',
        ['created_by'], ['employee_id'], ondelete='RESTRICT'
    )
    op.create_foreign_key(
        'fk_reward_categories_updated_by', 'reward_categories', 'employees',
        ['updated_by'], ['employee_id'], ondelete='RESTRICT'
    )
    op.create_foreign_key(
        'fk_reward_catalog_created_by', 'reward_catalog', 'employees',
        ['created_by'], ['employee_id'], ondelete='RESTRICT'
    )
    op.create_foreign_key(
        'fk_reward_catalog_updated_by', 'reward_catalog', 'employees',
        ['updated_by'], ['employee_id'], ondelete='RESTRICT'
    )
    op.create_foreign_key(
        'fk_transaction_types_created_by', 'transaction_types', 'employees',
        ['created_by'], ['employee_id'], ondelete='RESTRICT'
    )
    op.create_foreign_key(
        'fk_transaction_types_updated_by', 'transaction_types', 'employees',
        ['updated_by'], ['employee_id'], ondelete='RESTRICT'
    )


def downgrade() -> None:
    # 1. Drop circular foreign keys first
    op.drop_constraint('fk_transaction_types_updated_by', 'transaction_types', type_='foreignkey')
    op.drop_constraint('fk_transaction_types_created_by', 'transaction_types', type_='foreignkey')
    op.drop_constraint('fk_reward_catalog_updated_by', 'reward_catalog', type_='foreignkey')
    op.drop_constraint('fk_reward_catalog_created_by', 'reward_catalog', type_='foreignkey')
    op.drop_constraint('fk_reward_categories_updated_by', 'reward_categories', type_='foreignkey')
    op.drop_constraint('fk_reward_categories_created_by', 'reward_categories', type_='foreignkey')
    op.drop_constraint('fk_review_categories_updated_by', 'review_categories', type_='foreignkey')
    op.drop_constraint('fk_review_categories_created_by', 'review_categories', type_='foreignkey')
    op.drop_constraint('fk_employees_updated_by', 'employees', type_='foreignkey')
    op.drop_constraint('fk_employees_created_by', 'employees', type_='foreignkey')
    op.drop_constraint('fk_roles_updated_by', 'roles', type_='foreignkey')
    op.drop_constraint('fk_roles_created_by', 'roles', type_='foreignkey')
    op.drop_constraint('fk_status_master_updated_by', 'status_master', type_='foreignkey')
    op.drop_constraint('fk_status_master_created_by', 'status_master', type_='foreignkey')
    op.drop_constraint('fk_designations_updated_by', 'designations', type_='foreignkey')
    op.drop_constraint('fk_designations_created_by', 'designations', type_='foreignkey')
    op.drop_constraint('fk_departments_updated_by', 'departments', type_='foreignkey')
    op.drop_constraint('fk_departments_created_by', 'departments', type_='foreignkey')
    op.drop_constraint('fk_department_types_updated_by', 'department_types', type_='foreignkey')
    op.drop_constraint('fk_department_types_created_by', 'department_types', type_='foreignkey')

    # 2. Drop dependent tables
    op.drop_index('idx_route_permissions_route_key', table_name='route_permissions')
    op.drop_table('route_permissions')

    op.drop_index('idx_employee_roles_role_id', table_name='employee_roles')
    op.drop_index('idx_employee_roles_revoked_at', table_name='employee_roles')
    op.drop_index('idx_employee_roles_is_active', table_name='employee_roles')
    op.drop_index('idx_employee_roles_employee_id_is_active', table_name='employee_roles')
    op.drop_index('idx_employee_roles_employee_id', table_name='employee_roles')
    op.drop_index('idx_employee_roles_assigned_at', table_name='employee_roles')
    op.drop_table('employee_roles')

    op.drop_index('idx_reward_history_wallet_id', table_name='reward_history')
    op.drop_index('idx_reward_history_wallet_granted', table_name='reward_history')
    op.drop_index('idx_reward_history_granted_by', table_name='reward_history')
    op.drop_index('idx_reward_history_granted_at', table_name='reward_history')
    op.drop_index('idx_reward_history_catalog_id', table_name='reward_history')
    op.drop_index('idx_reward_history_catalog_granted', table_name='reward_history')
    op.drop_table('reward_history')

    op.drop_index('idx_transactions_wallet_transaction_at', table_name='transactions')
    op.drop_index('idx_transactions_wallet_status', table_name='transactions')
    op.drop_index('idx_transactions_wallet_id', table_name='transactions')
    op.drop_index('idx_transactions_transaction_type_id', table_name='transactions')
    op.drop_index('idx_transactions_transaction_at', table_name='transactions')
    op.drop_index('idx_transactions_status_id', table_name='transactions')
    op.drop_index('idx_transactions_created_at', table_name='transactions')
    op.drop_table('transactions')

    op.drop_index('idx_wallets_total_earned_points', table_name='wallets')
    op.drop_index('idx_wallets_available_points', table_name='wallets')
    op.drop_table('wallets')

    op.drop_index('idx_transaction_types_is_credit', table_name='transaction_types')
    op.drop_table('transaction_types')

    op.drop_index('idx_reward_catalog_min_max_points', table_name='reward_catalog')
    op.drop_index('idx_reward_catalog_is_active', table_name='reward_catalog')
    op.drop_index('idx_reward_catalog_category_is_active', table_name='reward_catalog')
    op.drop_index('idx_reward_catalog_category_id', table_name='reward_catalog')
    op.drop_table('reward_catalog')

    op.drop_index('idx_reward_categories_is_active', table_name='reward_categories')
    op.drop_table('reward_categories')

    op.drop_index('idx_review_category_tags_review_id', table_name='review_category_tags')
    op.drop_index('idx_review_category_tags_category_id', table_name='review_category_tags')
    op.drop_table('review_category_tags')

    op.drop_index('idx_reviews_status_id', table_name='reviews')
    op.drop_index('idx_reviews_reviewer_review_at', table_name='reviews')
    op.drop_index('idx_reviews_reviewer_id', table_name='reviews')
    op.drop_index('idx_reviews_review_at', table_name='reviews')
    op.drop_index('idx_reviews_receiver_status_id', table_name='reviews')
    op.drop_index('idx_reviews_receiver_review_at', table_name='reviews')
    op.drop_index('idx_reviews_receiver_raw_points', table_name='reviews')
    op.drop_index('idx_reviews_receiver_id', table_name='reviews')
    op.drop_table('reviews')

    op.drop_index('idx_review_categories_is_active', table_name='review_categories')
    op.drop_index('idx_review_categories_category_code', table_name='review_categories')
    op.drop_table('review_categories')

    op.drop_index('idx_refresh_tokens_token_hash', table_name='refresh_tokens')
    op.drop_index('idx_refresh_tokens_employee_id', table_name='refresh_tokens')
    op.drop_table('refresh_tokens')

    op.drop_index('idx_audit_log_table_record_performed', table_name='audit_log')
    op.drop_index('idx_audit_log_table_record', table_name='audit_log')
    op.drop_index('idx_audit_log_table_name', table_name='audit_log')
    op.drop_index('idx_audit_log_record_id', table_name='audit_log')
    op.drop_index('idx_audit_log_performed_by', table_name='audit_log')
    op.drop_index('idx_audit_log_performed_at', table_name='audit_log')
    op.drop_index('idx_audit_log_operation_type', table_name='audit_log')
    op.drop_table('audit_log')

    op.drop_index('idx_notifications_employee_id_is_read', table_name='notifications')
    op.drop_index('idx_notifications_employee_id', table_name='notifications')
    op.drop_index('idx_notifications_email_sent_type_send_created', table_name='notifications')
    op.drop_index('idx_notifications_created_at', table_name='notifications')
    op.drop_table('notifications')

    op.drop_index('idx_employees_status_id', table_name='employees')
    op.drop_index('idx_employees_manager_id_status_id', table_name='employees')
    op.drop_index('idx_employees_manager_id', table_name='employees')
    op.drop_index('idx_employees_designation_id', table_name='employees')
    op.drop_index('idx_employees_department_id_status_id', table_name='employees')
    op.drop_index('idx_employees_department_id', table_name='employees')
    op.drop_index('idx_employees_date_of_joining', table_name='employees')
    op.drop_index('idx_employees_date_of_birth', table_name='employees')
    op.drop_index('idx_employees_created_at', table_name='employees')
    op.drop_table('employees')

    op.drop_table('roles')

    op.drop_index('idx_status_master_entity_type_status_code', table_name='status_master')
    op.drop_index('idx_status_master_entity_type', table_name='status_master')
    op.drop_table('status_master')

    op.drop_index('idx_designations_level', table_name='designations')
    op.drop_index('idx_designations_is_active', table_name='designations')
    op.drop_table('designations')

    op.drop_index('idx_departments_department_type_id', table_name='departments')
    op.drop_table('departments')

    op.drop_table('department_types')