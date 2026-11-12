"""
src/wallet/dependencies.py
──────────────────────────
FastAPI dependency provider for WalletService.
"""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.wallet.repository import SQLAlchemyWalletRepository
from src.wallet.service import WalletService


def get_wallet_service(
    db: AsyncSession = Depends(get_db),
) -> WalletService:
    repo = SQLAlchemyWalletRepository(db)
    return WalletService(repo=repo)