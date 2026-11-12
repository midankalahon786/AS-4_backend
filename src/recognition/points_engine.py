"""
src/recognition/points_engine.py
────────────────────────────────
Stateless points calculation engine for the Recognition microservice.

All multipliers are pre-resolved from the database by the service layer
and passed in as floats. The engine has zero DB/IO dependencies and is
trivially unit-testable.

Formula:
    raw_points = sum(category_multipliers) × reviewer_weight
"""
from __future__ import annotations

from dataclasses import dataclass


# ──────────────────────────────────────────────────────────────
# 1. RESULT CONTAINER
# ──────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class PointsResult:
    """
    Carries intermediate values for audit logging and downstream events.

    category_code is a human-readable label (or comma-joined labels) for
    logging/audit; it is not used in the calculation.
    """
    category_code: str
    total_category_multiplier: float
    reviewer_weight: float
    raw_points: float

    def as_dict(self) -> dict[str, float | str]:
        return {
            "category_code": self.category_code,
            "total_category_multiplier": self.total_category_multiplier,
            "reviewer_weight": self.reviewer_weight,
            "raw_points": round(self.raw_points, 4),
        }


# ──────────────────────────────────────────────────────────────
# 2. CALCULATION ENGINE
# ──────────────────────────────────────────────────────────────

def calculate_points(
    *,
    total_category_multiplier: float,
    reviewer_weight: float,
    category_code: str = "",
) -> PointsResult:
    """
    Pure calculation entry point.

    Parameters
    ----------
    total_category_multiplier : float
        Sum of selected review_categories multipliers.
    reviewer_weight : float
        Weight resolved from the employee's active roles.
    category_code : str
        Labels for logging/audit tracking.

    Returns
    -------
    PointsResult with calculated raw_points.
    """
    raw = total_category_multiplier * reviewer_weight

    return PointsResult(
        category_code=category_code,
        total_category_multiplier=total_category_multiplier,
        reviewer_weight=reviewer_weight,
        raw_points=raw,
    )