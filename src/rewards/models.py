import uuid
from datetime import datetime
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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base
from src.employees.models import Employee
from src.wallet.models import Wallet

class RewardCategory(Base):
    __tablename__ = "reward_categories"
    __table_args__ = (
        Index("idx_reward_categories_is_active", "is_active"),
    )

    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    category_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    category_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id", ondelete="RESTRICT"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id", ondelete="RESTRICT"), nullable=True
    )

    reward_catalog: Mapped[list["RewardCatalog"]] = relationship("RewardCatalog", back_populates="category")


class RewardCatalog(Base):
    __tablename__ = "reward_catalog"
    __table_args__ = (
        Index("idx_reward_catalog_category_id", "category_id"),
        Index("idx_reward_catalog_category_is_active", "category_id", "is_active"),
        Index("idx_reward_catalog_is_active", "is_active"),
        Index("idx_reward_catalog_min_max_points", "min_points", "max_points"),
    )

    catalog_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    reward_name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    reward_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_points: Mapped[int] = mapped_column(Integer, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reward_categories.category_id"), nullable=False
    )
    min_points: Mapped[int] = mapped_column(Integer, nullable=False)
    max_points: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id", ondelete="RESTRICT"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id", ondelete="RESTRICT"), nullable=True
    )
    available_stock: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    category: Mapped["RewardCategory"] = relationship("RewardCategory", back_populates="reward_catalog")
    history_records: Mapped[list["RewardHistory"]] = relationship("RewardHistory", back_populates="catalog_item")


class RewardHistory(Base):
    __tablename__ = "reward_history"
    __table_args__ = (
        Index("idx_reward_history_catalog_granted", "catalog_id", "granted_at"),
        Index("idx_reward_history_catalog_id", "catalog_id"),
        Index("idx_reward_history_granted_at", "granted_at"),
        Index("idx_reward_history_granted_by", "granted_by"),
        Index("idx_reward_history_wallet_granted", "wallet_id", "granted_at"),
        Index("idx_reward_history_wallet_id", "wallet_id"),
    )

    history_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallets.wallet_id", ondelete="CASCADE"), nullable=False
    )
    catalog_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reward_catalog.catalog_id"), nullable=False
    )
    granted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id"), nullable=False
    )
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id"), nullable=False
    )

    catalog_item: Mapped["RewardCatalog"] = relationship("RewardCatalog", back_populates="history_records")
    granted_by_employee: Mapped["Employee"] = relationship("Employee", foreign_keys=[granted_by])
    wallet: Mapped["Wallet"] = relationship("Wallet", foreign_keys=[wallet_id])