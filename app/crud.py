from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List, Dict, Any

from . import models, schemas
from .dependencies import pwd_context # 비밀번호 처리를 위해 dependencies에서 가져옴

# =================================================================
#                         사용자 (User)
# =================================================================

async def get_user_by_email(db: AsyncSession, email: str) -> models.User | None:
    """
    이메일을 기준으로 사용자를 조회합니다.
    """
    result = await db.execute(select(models.User).filter(models.User.email == email))
    return result.scalar_one_or_none()

async def create_user(db: AsyncSession, user: schemas.UserCreate) -> models.User:
    """
    새로운 사용자를 생성합니다.
    """
    hashed_password = pwd_context.hash(user.password)
    db_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user


# =================================================================
#                         계약서 (Contract)
# =================================================================

async def create_contract(db: AsyncSession, contract: schemas.ContractCreate, user_id: int) -> models.Contract:
    """
    새로운 계약서를 생성합니다.
    """
    db_contract = models.Contract(
        contract_type=contract.contract_type,
        owner_id=user_id,
        content={} # 초기 content는 빈 JSON 객체로 설정
    )
    db.add(db_contract)
    await db.commit()
    await db.refresh(db_contract)
    return db_contract

async def get_contracts_by_owner(db: AsyncSession, user_id: int) -> List[models.Contract]:
    """
    특정 사용자가 생성한 모든 계약서 목록을 조회합니다.
    """
    result = await db.execute(
        select(models.Contract)
        .filter(models.Contract.owner_id == user_id)
        .order_by(models.Contract.updated_at.desc()) # 최신순으로 정렬
    )
    return result.scalars().all()

async def get_contract_by_id(db: AsyncSession, contract_id: int, user_id: int) -> models.Contract | None:
    """
    특정 계약서의 상세 정보를 조회합니다.
    이때, 해당 계약서의 소유자가 맞는지도 함께 확인합니다.
    """
    result = await db.execute(
        select(models.Contract)
        .filter(models.Contract.id == contract_id, models.Contract.owner_id == user_id)
    )
    return result.scalar_one_or_none()

async def update_contract_content(db: AsyncSession, contract: models.Contract, field_id: str, value: Any) -> models.Contract:
    """
    특정 계약서의 content 필드를 업데이트합니다.
    챗봇과의 대화를 통해 실시간으로 계약서 내용을 채워나갈 때 사용됩니다.
    """
    # 기존 content를 가져와 새로운 내용으로 업데이트
    current_content = contract.content or {}
    current_content[field_id] = value
    
    # SQLAlchemy 2.0+ 에서는 JSON 컬럼 수정을 위해 update 구문을 사용하는 것이 효율적입니다.
    stmt = (
        update(models.Contract)
        .where(models.Contract.id == contract.id)
        .values(content=current_content)
    )
    await db.execute(stmt)
    await db.commit()
    await db.refresh(contract)
    
    return contract

