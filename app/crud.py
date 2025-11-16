from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from typing import List, Any, Dict
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

async def update_contract_content_multiple(db: AsyncSession, contract: models.Contract, fields_to_update: Dict[str, Any]) -> models.Contract:
    """
    AI가 반환한 여러 필드를 계약서 content에 한 번에 병합(merge)하여 업데이트합니다.
    """
    # 1. DB에서 현재 content를 가져옵니다 (불변성 유지를 위해 복사)
    current_content = dict(contract.content) if contract.content else {}
    
    # 2. AI가 새로 채운 필드들을 덮어씁니다. (예: 'is_bonus_paid_no_o'와 'bonus_amount' 동시 저장)
    current_content.update(fields_to_update)
    
    # 3. DB에 반영합니다.
    contract.content = current_content
    db.add(contract)
    await db.commit()
    await db.refresh(contract, attribute_names=['content'])
    print(f"DEBUG_3: Contract Content AFTER DB Save: {contract.content.get('employee_name')}") # 디버그 출력 유지
    
    return contract


async def delete_contract(db: AsyncSession, contract: models.Contract):
    """
    데이터베이스에서 특정 계약서 객체를 삭제합니다.
    (라우터에서 전달받은 contract 객체의 ID를 사용합니다.)
    """
    
    # ❗️ (수정) db.delete(contract) 대신,
    # contract.id를 기준으로 DB에 직접 DELETE SQL을 실행합니다.
    # (contracts.py에서 이미 소유권 검사를 마쳤으므로 안전합니다.)
    stmt = delete(models.Contract).where(models.Contract.id == contract.id)
    
    await db.execute(stmt)
    await db.commit()
    return None

async def update_contract(db: AsyncSession, contract_id: UUID, new_content: Dict[str, Any], new_chat_history: List[Dict[str, Any]]) -> models.Contract:
    """
    계약서 content 전체를 덮어써서 업데이트하는 함수
    services.py의 process_chat_message()가 호출함
    """
    stmt = (
        update(models.Contract)
        .where(models.Contract.id == contract_id)
        .values(content=new_content, chat_history=new_chat_history)
        #.execution_options(synchronize_session="fetch")
    )

    await db.execute(stmt)
    await db.commit()

    updated = await db.get(models.Contract, contract_id)
    return updated
