from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List, Any

from . import models, schemas
# dependencies.py 대신 security.py에서 비밀번호 관련 함수를 가져옵니다.
from .security import get_password_hash, verify_password

# =================================================================
#                         사용자 (User) with SQLAlchemy
# =================================================================

async def get_user_by_email(db: AsyncSession, email: str) -> models.User | None:
    """이메일을 기준으로 사용자를 조회합니다."""
    result = await db.execute(select(models.User).filter(models.User.email == email))
    return result.scalar_one_or_none()

async def create_user(db: AsyncSession, user: schemas.UserSignUp) -> models.User:
    """SQLAlchemy를 사용해 새로운 사용자를 생성합니다."""
    # security.py에 있는 get_password_hash 함수를 사용합니다.
    hashed_password = get_password_hash(user.password)
    db_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user

async def authenticate_user(db: AsyncSession, email: str, password: str) -> models.User | None:
    """SQLAlchemy를 사용해 사용자를 인증합니다."""
    user = await get_user_by_email(db, email)
    # security.py에 있는 verify_password 함수를 사용합니다.
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


# =================================================================
#                         계약서 (Contract) with SQLAlchemy
# =================================================================

async def create_contract(db: AsyncSession, contract: schemas.ContractCreate, user_id: int) -> models.Contract:
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

async def get_contracts_by_owner(db: AsyncSession, user_id: int) -> List[models.Contract]:
    """특정 사용자가 생성한 모든 계약서 목록을 조회합니다."""
    result = await db.execute(
        select(models.Contract)
        .filter(models.Contract.owner_id == user_id)
        .order_by(models.Contract.updated_at.desc())
    )
    return result.scalars().all()

async def get_contract_by_id(db: AsyncSession, contract_id: int, user_id: int) -> models.Contract | None:
    """특정 계약서의 상세 정보를 조회합니다."""
    result = await db.execute(
        select(models.Contract)
        .filter(models.Contract.id == contract_id, models.Contract.owner_id == user_id)
    )
    return result.scalar_one_or_none()

async def update_contract_content(db: AsyncSession, contract: models.Contract, field_id: str, value: Any) -> models.Contract:
    """특정 계약서의 content 필드를 업데이트합니다."""
    current_content = contract.content or {}
    current_content[field_id] = value
    
    stmt = (
        update(models.Contract)
        .where(models.Contract.id == contract.id)
        .values(content=current_content)
    )
    await db.execute(stmt)
    await db.commit()
    await db.refresh(contract)
    
    return contract

