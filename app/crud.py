from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List, Any
from uuid import UUID

from . import models, schemas
# dependencies.py 대신 security.py에서 비밀번호 관련 함수를 가져옵니다.
from .security import get_password_hash, verify_password

# =================================================================
#               기존 사용자 관리 함수 (모두 삭제)
# =================================================================
# create_user, get_user_by_email, authenticate_user 함수는
# 이제 routers/users.py에서 Supabase 클라이언트로 직접 처리하므로 삭제합니다.

# =================================================================
#               프로필 (Profile) - 필요 시 추가
# =================================================================

async def get_profile_by_id(db: AsyncSession, user_id: UUID) -> models.Profile | None:
    """사용자 ID(UUID)를 기준으로 프로필을 조회합니다."""
    result = await db.execute(select(models.Profile).filter(models.Profile.id == user_id))
    return result.scalar_one_or_none()

# =================================================================
#                         계약서 (Contract) with SQLAlchemy
# =================================================================

async def create_contract(db: AsyncSession, contract: schemas.ContractCreate, user_id: UUID) -> models.Contract:
    """새로운 계약서를 생성합니다."""
    db_contract = models.Contract(
        contract_type=contract.contract_type,
        owner_id=user_id,
        content={}
    )
    db.add(db_contract)
    await db.commit()
    await db.refresh(db_contract)
    return db_contract

async def get_contracts_by_owner(db: AsyncSession, user_id: UUID) -> List[models.Contract]:
    """특정 사용자가 생성한 모든 계약서 목록을 조회합니다."""
    result = await db.execute(
        select(models.Contract)
        .filter(models.Contract.owner_id == user_id)
        .order_by(models.Contract.updated_at.desc())
    )
    return result.scalars().all()

async def get_contract_by_id(db: AsyncSession, contract_id: UUID, user_id: UUID) -> models.Contract | None:
    """특정 계약서의 상세 정보를 조회합니다."""
    result = await db.execute(
        select(models.Contract)
        .filter(models.Contract.id == contract_id, models.Contract.owner_id == user_id)
    )
    return result.scalar_one_or_none()

async def update_contract_content(db: AsyncSession, contract: models.Contract, field_id: str, value: Any) -> models.Contract:
    """특정 계약서의 content 필드를 업데이트합니다."""
    #current_content = contract.content or {}
    current_content = dict(contract.content) if contract.content else {}
    current_content[field_id] = value
    
    """stmt = (
        update(models.Contract)
        .where(models.Contract.id == contract.id)
        .values(content=current_content)
    )
    await db.execute(stmt)
    await db.commit()
    await db.refresh(contract)"""
    
    contract.content = current_content
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    
    return contract

