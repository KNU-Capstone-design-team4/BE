import io
import os
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from .. import crud, schemas, models, services # services.py를 만들어 AI 로직을 넣을 예정
from ..database import get_db
from ..dependencies import verify_supabase_token 
from uuid import UUID
from urllib.parse import quote

router = APIRouter(
    prefix="/api/contracts",
    tags=["contracts"],
    dependencies=[Depends(verify_supabase_token)] # 이 라우터의 모든 API는 로그인이 필요함
)

@router.post("", response_model=schemas.ContractDetail, status_code=status.HTTP_201_CREATED)
async def create_new_contract(
    contract_data: schemas.ContractCreate,
    db: AsyncSession = Depends(get_db),
    #current_user: models.User = Depends(verify_supabase_token)
    current_user: dict = Depends(verify_supabase_token)
):
    """
    ### 새 계약서 생성
    - **로그인된 사용자**를 위해 새로운 계약서 작성 세션을 시작합니다.
    - 요청 Body에 `contract_type` (예: "근로계약서")을 담아 보냅니다.
    - 성공 시 생성된 계약서의 상세 정보를 반환합니다.
    """
    return await crud.create_contract(db=db, contract=contract_data, user_id=UUID(current_user['id']))

@router.get("", response_model=List[schemas.ContractInfo])
async def get_my_contracts(
    db: AsyncSession = Depends(get_db),
    #current_user: models.User = Depends(verify_supabase_token)
    current_user: dict = Depends(verify_supabase_token)
):
    """
    ### 내 계약서 목록 조회
    - 현재 **로그인된 사용자**가 작성한 모든 계약서의 목록을 조회합니다.
    - 마이페이지 기능에 사용됩니다.
    """
    return await crud.get_contracts_by_owner(db=db, user_id=UUID(current_user['id']))

@router.get("/{contract_id}", response_model=schemas.ContractDetail)
async def get_contract_details(
    contract_id: UUID,
    db: AsyncSession = Depends(get_db),
    #current_user: models.User = Depends(verify_supabase_token)
    current_user: dict = Depends(verify_supabase_token)
):
    """
    ### 특정 계약서 상세 조회
    - 계약서의 현재 상태('status')와
    - '미완성' 상태일 경우 이어서 물어볼 'next_question'을 함께 반환합니다.
    """
    user_id = UUID(current_user['id'])
    db_contract = await crud.get_contract_by_id(db=db, contract_id=contract_id, user_id=user_id)
    if db_contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계약서를 찾을 수 없거나 접근 권한이 없습니다.")
    
    # -----------------------------------------------------------
    # ❗️ [핵심 로직 추가] ❗️
    # -----------------------------------------------------------
    # 1. services.py에 다음 질문을 찾는 헬퍼 함수 호출
    next_question_text = services.find_next_question(db_contract)

    # 2. 계약서 상태 업데이트 (필요시)
    current_status = db_contract.status
    if next_question_text is None and db_contract.status == "in_progress":
        # 다음 질문이 없는데 상태가 '진행중'이면 '완료'로 변경
        db_contract = await crud.update_contract_status(db, db_contract, "completed")
        current_status = "completed"

    # 3. Pydantic 스키마가 from_attributes=True 이므로,
    #    조회한 객체에 동적으로 속성을 추가하여 반환할 수 있습니다.
    db_contract.next_question = next_question_text
    db_contract.status = current_status # DB에서 읽어온 status (또는 방금 변경한 status)
    
    # ✅ [핵심 추가] HTML 템플릿 읽기
    html_path = os.path.join(os.path.dirname(__file__), "..", "templates", "working.html")
    html_path = os.path.abspath(html_path)
    
    if not os.path.exists(html_path):
        raise HTTPException(status_code=500, detail=f"템플릿 파일을 찾을 수 없습니다: {html_path}")

    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    
     # ContractDetail 스키마를 확장해 templateHtml 필드를 포함시켰다고 가정
    return {
        "id": str(db_contract.id),
        "title": db_contract.title,
        "status": db_contract.status,
        "next_question": db_contract.next_question,
        "data": db_contract.content,
        "templateHtml": html_content,   # ✅ 프론트에서 미리보기용으로 사용할 HTML
        "chatHistory": db_contract.chat_history if hasattr(db_contract, "chat_history") else [],
    }

@router.post("/{contract_id}/chat", response_model=schemas.ChatResponse)
async def chat_with_bot(
    contract_id: UUID,
    chat_data: schemas.ChatRequest,
    db: AsyncSession = Depends(get_db),
    #current_user: models.User = Depends(verify_supabase_token)
    current_user: dict = Depends(verify_supabase_token)
):
    """
    ### 챗봇과 대화 (계약서 업데이트)
    - 사용자의 채팅 메시지를 받아 계약서 내용을 업데이트하고, 다음 질문을 반환합니다.
    - **실시간 계약서 업데이트**의 핵심 API입니다.
    """
    db_contract = await crud.get_contract_by_id(db=db, contract_id=contract_id, user_id=UUID(current_user['id']))
    if db_contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계약서를 찾을 수 없거나 접근 권한이 없습니다.")

    # 실제 AI 로직은 services.py에서 처리
    response = await services.process_chat_message(db, db_contract, chat_data.message)
    return response

@router.delete("/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contract(
    contract_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(verify_supabase_token)
):
    """
    ### 특정 계약서 삭제
    ... (주석 동일) ...
    """
    db_contract = await crud.get_contract_by_id(db=db, contract_id=contract_id, user_id=UUID(current_user['id']))
    
    if db_contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계약서를 찾을 수 없거나 접근 권한이 없습니다.")
    
    await crud.delete_contract(db=db, contract=db_contract)
    
    # ❗️ 수정된 부분:
    # 204 응답은 본문이 없으므로, 아무것도 반환하지 않습니다.
    # 데코레이터가 status_code=204를 알아서 처리해 줍니다.
    return None

@router.get("/{contract_id}/download")
async def download_contract(
    contract_id: UUID,
    db: AsyncSession = Depends(get_db),
    #current_user: models.User = Depends(verify_supabase_token)
    current_user: dict = Depends(verify_supabase_token)
):
    """
    ### 계약서 다운로드
    - 완성된 계약서를 **.docx (워드)** 파일로 다운로드합니다.
    """
    db_contract = await crud.get_contract_by_id(db=db, contract_id=contract_id, user_id=UUID(current_user['id']))
    if db_contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계약서를 찾을 수 없거나 접근 권한이 없습니다.")
    
    # 실제 문서 생성 로직은 services.py에서 처리
    document = await services.create_docx_from_contract(db_contract)
    
    # 파일을 메모리 버퍼에 저장하여 전송
    buffer = io.BytesIO()
    document.save(buffer)
    buffer.seek(0)
    
    # 1. 원본 파일 이름을 생성합니다.
    filename = f"{db_contract.contract_type}_{db_contract.id}.docx"
    
    # 2. 파일 이름을 UTF-8로 URL 인코딩합니다.
    encoded_filename = quote(filename)

    # 3. 표준에 맞는 Content-Disposition 헤더를 설정합니다.
    headers = {
        'Content-Disposition': f'attachment; filename*=UTF-8\'\'{encoded_filename}'
    }
    
    '''filename = f"{db_contract.contract_type}_{db_contract.id}.docx"
    headers = {'Content-Disposition': f'attachment; filename="{filename}"'}
    '''
    return StreamingResponse(buffer, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers=headers)

