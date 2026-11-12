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
from src.employees.models import Employee, StatusMaster

class Wallet(Base):
    __tablename__ = "wallets"
    __table_args__ = (
        Index("idx_wallets_available_points", "available_points"),
        Index("idx_wallets_total_earned_points", "total_earned_points"),
    )

    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id", ondelete="CASCADE"), unique=True, nullable=False
    )
    available_points: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    redeemed_points: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    total_earned_points: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id"), nullable=False
    )

    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction", back_populates="wallet", cascade="all, delete-orphan"
    )


class TransactionType(Base):
    __tablename__ = "transaction_types"
    __table_args__ = (
        Index("idx_transaction_types_is_credit", "is_credit"),
    )

    type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    type_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    type_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_credit: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id", ondelete="RESTRICT"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id", ondelete="RESTRICT"), nullable=True
    )

    transactions: Mapped[list["Transaction"]] = relationship("Transaction", back_populates="transaction_type")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("idx_transactions_created_at", "created_at"),
        Index("idx_transactions_status_id", "status_id"),
        Index("idx_transactions_transaction_at", "transaction_at"),
        Index("idx_transactions_transaction_type_id", "transaction_type_id"),
        Index("idx_transactions_wallet_id", "wallet_id"),
        Index("idx_transactions_wallet_status", "wallet_id", "status_id"),
        Index("idx_transactions_wallet_transaction_at", "wallet_id", "transaction_at"),
    )

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallets.wallet_id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    transaction_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transaction_types.type_id"), nullable=False
    )
    status_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("status_master.status_id"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    transaction_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id"), nullable=False
    )

    wallet: Mapped["Wallet"] = relationship("Wallet", back_populates="transactions")
    transaction_type: Mapped["TransactionType"] = relationship("TransactionType", foreign_keys=[transaction_type_id],
    lazy="joined", back_populates="transactions")
    status_master: Mapped["StatusMaster"] = relationship(
        "StatusMaster", lazy="joined"
    )
    @property
    def transaction_types(self) -> "TransactionType":
        return self.transaction_type

PointTransaction = Transaction