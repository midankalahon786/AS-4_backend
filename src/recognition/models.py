import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database import Base
from src.employees.models import Employee

class ReviewCategory(Base):
    __tablename__ = "review_categories"
    __table_args__ = (
        Index("idx_review_categories_category_code", "category_code"),
        Index("idx_review_categories_is_active", "is_active"),
    )

    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    category_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    category_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    multiplier: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
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

    review_category_tags: Mapped[list["ReviewCategoryTag"]] = relationship(
        "ReviewCategoryTag", back_populates="category"
    )


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        Index("idx_reviews_receiver_id", "receiver_id"),
        Index("idx_reviews_receiver_raw_points", "receiver_id", "raw_points"),
        Index("idx_reviews_receiver_review_at", "receiver_id", "review_at"),
        Index("idx_reviews_receiver_status_id", "receiver_id", "status_id"),
        Index("idx_reviews_review_at", "review_at"),
        Index("idx_reviews_reviewer_id", "reviewer_id"),
        Index("idx_reviews_reviewer_review_at", "reviewer_id", "review_at"),
        Index("idx_reviews_status_id", "status_id"),
    )

    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id"), nullable=False
    )
    receiver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id"), nullable=False
    )
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("status_master.status_id"), nullable=False
    )
    review_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id"), nullable=False
    )
    raw_points: Mapped[float | None] = mapped_column(Float, nullable=True)

    review_category_tags: Mapped[list["ReviewCategoryTag"]] = relationship(
        "ReviewCategoryTag", back_populates="review", cascade="all, delete-orphan"
    )
    reviewer_employee: Mapped["Employee"] = relationship("Employee", foreign_keys=[reviewer_id])
    receiver_employee: Mapped["Employee"] = relationship("Employee", foreign_keys=[receiver_id])


class ReviewCategoryTag(Base):
    __tablename__ = "review_category_tags"
    __table_args__ = (
        UniqueConstraint("review_id", "category_id", name="uq_review_category_tags_review_category"),
        Index("idx_review_category_tags_category_id", "category_id"),
        Index("idx_review_category_tags_review_id", "review_id"),
    )

    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reviews.review_id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("review_categories.category_id"), nullable=False
    )
    multiplier_snapshot: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    category_code_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    review: Mapped["Review"] = relationship("Review", back_populates="review_category_tags")
    category: Mapped["ReviewCategory"] = relationship("ReviewCategory", back_populates="review_category_tags")