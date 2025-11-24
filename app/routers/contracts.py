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
from app.schemas import ContractUpdate

TEMPLATE_MAPPING = {
    "근로계약서": "working.html",
    "통합신청서": "foreign.html",
    "임대차계약서": "house.html"
    # "다른계약서": "other_template.html",
}

WELCOME_MESSAGES = {
    "근로계약서": "안녕하세요!  근로계약서 작성 도우미 LAW BOT입니다.",
    "통합신청서": "안녕하세요!  통합신청서 작성을 도와드릴 LAW BOT입니다.",
    "임대차계약서": "안녕하세요! 임대차계약서 작성을 도와드릴 LAW BOT입니다."
    # 여기에 다른 계약서 종류도 추가하면 됩니다.
}

router = APIRouter(
    prefix="/api/contracts",
    tags=["contracts"],
    dependencies=[Depends(verify_supabase_token)] # 이 라우터의 모든 API는 로그인이 필요함
)

'''@router.post("", response_model=schemas.ContractDetail, status_code=status.HTTP_201_CREATED)
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
    return await crud.create_contract(db=db, contract=contract_data, user_id=UUID(current_user['id']))'''

@router.post("", response_model=schemas.ContractDetail, status_code=status.HTTP_201_CREATED)
async def create_new_contract(
    contract_data: schemas.ContractCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(verify_supabase_token)
):
    """
    ### 새 계약서 생성
    - 계약서를 생성함과 동시에 **첫 번째 인사말과 질문을 채팅 내역에 저장**합니다.
    - 프론트엔드에서 채팅창을 열자마자 봇의 메시지가 보이게 됩니다.
    """
    
    # 1. 계약서 DB 생성 (기존 로직) -> id, owner_id, content={} 상태로 생성됨
    new_contract = await crud.create_contract(db=db, contract=contract_data, user_id=UUID(current_user['id']))
    
    # -----------------------------------------------------------
    # 🤖 봇의 첫 메시지 생성 및 저장 로직
    # -----------------------------------------------------------
    
    # 2. services를 통해 첫 번째 질문 찾기 (content가 비어있으므로 첫 질문이 나옴)
    first_question = services.find_next_question(new_contract)
    
    # 3. 계약서 타입에 맞는 인사말 가져오기
    welcome_msg = WELCOME_MESSAGES.get(contract_data.contract_type, "안녕하세요! LAW BOT입니다.")
    
    # 4. 봇의 메시지 구성 (인사말 + 줄바꿈 + 첫 질문)
    full_bot_message = f"{welcome_msg}\n\n{first_question}" if first_question else welcome_msg
    
    # 5. 초기 채팅 내역 리스트 생성
    initial_chat_history = [
        {
            "role": "assistant", 
            "message": welcome_msg 
        }
    ]
    # 6. DB 업데이트 (crud.update_contract 활용)
    # crud.update_contract는 content와 chat_history를 모두 받으므로,
    # 기존 content(빈 딕셔너리)는 그대로 유지하고 chat_history만 채워서 보냅니다.
    updated_contract = await crud.update_contract(
        db=db,
        contract_id=new_contract.id,
        new_content=new_contract.content,       # 기존 내용 유지 ({})
        new_chat_history=initial_chat_history   # 인사말 추가
    )

    # 7. 업데이트된 계약서 반환 (이제 chat_history에 첫 인사가 포함됨)
    return updated_contract


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
    
    contract_type = db_contract.contract_type
    template_filename = TEMPLATE_MAPPING.get(contract_type)
    if template_filename is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"'{contract_type}' 유형의 계약서는 HTML 미리보기를 지원하지 않습니다."
        )
    
    # ✅ [핵심 추가] HTML 템플릿 읽기
    html_path = os.path.join(os.path.dirname(__file__), "..", "..", "templates", template_filename)
    html_path = os.path.abspath(html_path)
    
    
    if not os.path.exists(html_path):
        raise HTTPException(status_code=500, detail=f"템플릿 파일을 찾을 수 없습니다: {html_path}")

    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    
     # ContractDetail 스키마를 확장해 templateHtml 필드를 포함시켰다고 가정
    return {
        "id": str(db_contract.id),
        "contract_type": db_contract.contract_type,
        "status": db_contract.status,
        "updated_at": db_contract.updated_at,
        "owner_id": db_contract.owner_id,
        "next_question": db_contract.next_question,
        "content": db_contract.content,
        "templateHtml": html_content,   # ✅ 프론트에서 미리보기용으로 사용할 HTML
        "chat_history": db_contract.chat_history if hasattr(db_contract, "chat_history") else [],
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

@router.patch("/{contract_id}/content")
async def update_contract_content(
    contract_id: str,  # URL에서 문자열로 받음
    update_data: ContractUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(verify_supabase_token) # 인증 필요
):
    # 1. 문자열 ID를 UUID 객체로 변환 (crud 함수 타입 힌트에 맞춤)
    try:
        contract_uuid = UUID(contract_id)
        user_uuid = UUID(current_user['id'])
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    # 2. 계약서 조회 (crud.py의 함수 이름 사용!)
    contract = await crud.get_contract_by_id(db, contract_id=contract_uuid, user_id=user_uuid)
    
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    # 3. 기존 내용에 새로운 내용 병합 (Merge)
    current_content = dict(contract.content) if contract.content else {}
    current_content.update(update_data.content)
    
    # 4. DB 저장 (crud.py에 있는 업데이트 함수 재사용 가능)
    #    update_contract_content_multiple 함수가 이미 구현되어 있으니 이걸 쓰면 깔끔합니다!
    updated_contract = await crud.update_contract_content_multiple(
        db=db, 
        contract=contract, 
        fields_to_update=update_data.content
    )
    
    return {"status": "success", "content": updated_contract.content}

