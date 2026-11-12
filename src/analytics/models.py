import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base

class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("idx_audit_log_operation_type", "operation_type"),
        Index("idx_audit_log_performed_at", "performed_at"),
        Index("idx_audit_log_performed_by", "performed_by"),
        Index("idx_audit_log_record_id", "record_id"),
        Index("idx_audit_log_table_name", "table_name"),
        Index("idx_audit_log_table_record", "table_name", "record_id"),
        Index("idx_audit_log_table_record_performed", "table_name", "record_id", "performed_at"),
    )

    audit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    table_name: Mapped[str] = mapped_column(String(100), nullable=False)
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    old_values: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    new_values: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    performed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id"), nullable=False
    )
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

# Re-export Notification from src.notifications.models to avoid duplicate MetaData definition
from src.notifications.models import Notification