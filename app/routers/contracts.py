import io
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from .. import crud, schemas, models, services # services.py를 만들어 AI 로직을 넣을 예정
from ..database import get_db
from ..dependencies import get_current_user
from docx import Document

router = APIRouter(
    prefix="/api/contracts",
    tags=["contracts"],
    dependencies=[Depends(get_current_user)] # 이 라우터의 모든 API는 로그인이 필요함
)

@router.post("", response_model=schemas.ContractDetail, status_code=status.HTTP_201_CREATED)
async def create_new_contract(
    contract_data: schemas.ContractCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    ### 새 계약서 생성
    - **로그인된 사용자**를 위해 새로운 계약서 작성 세션을 시작합니다.
    - 요청 Body에 `contract_type` (예: "근로계약서")을 담아 보냅니다.
    - 성공 시 생성된 계약서의 상세 정보를 반환합니다.
    """
    return await crud.create_contract(db=db, contract=contract_data, user_id=current_user.id)

@router.get("", response_model=List[schemas.ContractInfo])
async def get_my_contracts(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    ### 내 계약서 목록 조회
    - 현재 **로그인된 사용자**가 작성한 모든 계약서의 목록을 조회합니다.
    - 마이페이지 기능에 사용됩니다.
    """
    return await crud.get_contracts_by_owner(db=db, user_id=current_user.id)

@router.get("/{contract_id}", response_model=schemas.ContractDetail)
async def get_contract_details(
    contract_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    ### 특정 계약서 상세 조회
    - 특정 계약서의 상세 내용을 조회합니다.
    - 다른 사람의 계약서는 조회할 수 없습니다.
    """
    db_contract = await crud.get_contract_by_id(db=db, contract_id=contract_id, user_id=current_user.id)
    if db_contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계약서를 찾을 수 없거나 접근 권한이 없습니다.")
    return db_contract

@router.post("/{contract_id}/chat", response_model=schemas.ChatResponse)
async def chat_with_bot(
    contract_id: int,
    chat_data: schemas.ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    ### 챗봇과 대화 (계약서 업데이트)
    - 사용자의 채팅 메시지를 받아 계약서 내용을 업데이트하고, 다음 질문을 반환합니다.
    - **실시간 계약서 업데이트**의 핵심 API입니다.
    """
    db_contract = await crud.get_contract_by_id(db=db, contract_id=contract_id, user_id=current_user.id)
    if db_contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계약서를 찾을 수 없거나 접근 권한이 없습니다.")

    # 실제 AI 로직은 services.py에서 처리
    response = await services.process_chat_message(db, db_contract, chat_data.message)
    return response

@router.get("/{contract_id}/download")
async def download_contract(
    contract_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    ### 계약서 다운로드
    - 완성된 계약서를 **.docx (워드)** 파일로 다운로드합니다.
    """
    db_contract = await crud.get_contract_by_id(db=db, contract_id=contract_id, user_id=current_user.id)
    if db_contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계약서를 찾을 수 없거나 접근 권한이 없습니다.")
    
    # 실제 문서 생성 로직은 services.py에서 처리
    document = services.create_docx_from_contract(db_contract)
    
    # 파일을 메모리 버퍼에 저장하여 전송
    buffer = io.BytesIO()
    document.save(buffer)
    buffer.seek(0)
    
    filename = f"{db_contract.contract_type}_{db_contract.id}.docx"
    headers = {'Content-Disposition': f'attachment; filename="{filename}"'}
    
    return StreamingResponse(buffer, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers=headers)

