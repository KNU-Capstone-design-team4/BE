from sqlalchemy.ext.asyncio import AsyncSession
from docx import Document

from . import crud, models, schemas

# 계약서 종류별로 필요한 필드와 질문 순서를 정의합니다.
# 프론트엔드와 이 field_id를 기준으로 화면을 업데이트하기로 약속해야 합니다.
CONTRACT_SCENARIOS = {
    "근로계약서": [
        {"field_id": "employee_name", "question": "먼저 근로자의 성함은 무엇인가요?"},
        {"field_id": "employee_resident_number", "question": "근로자의 주민등록번호를 알려주세요."},
        {"field_id": "employee_address", "question": "근로자의 주소는 어디인가요?"},
        {"field_id": "salary_amount", "question": "월 급여는 얼마로 계약하셨나요?"},
        # ... 추가 질문들 ...
    ],
    "임대차계약서": [
        {"field_id": "lessee_name", "question": "안녕하세요! 계약서 작성을 시작하겠습니다. 임차인의 성함은 무엇인가요?"},
        {"field_id": "property_address", "question": "계약할 부동산의 정확한 주소는 어디인가요?"},
        {"field_id": "deposit_amount", "question": "보증금은 얼마인가요?"},
        {"field_id": "rent_amount", "question": "월 차임(월세)은 얼마인가요?"},
        # ... 추가 질문들 ...
    ]
}

async def process_chat_message(db: AsyncSession, contract: models.Contract, user_message: str):
    """
    사용자 메시지를 처리하고, 계약서를 업데이트하며, 다음 챗봇 응답을 생성합니다.
    """
    # 1. 현재 계약서의 시나리오와 진행 상태를 파악합니다.
    scenario = CONTRACT_SCENARIOS.get(contract.contract_type, [])
    current_content = contract.content or {}
    
    # 2. 현재 답변이 어떤 질문에 대한 것인지 찾습니다.
    current_question_item = None
    for item in scenario:
        if item["field_id"] not in current_content:
            current_question_item = item
            break

    updated_field_info = None
    if current_question_item:
        # 3. AI(LLM)를 호출하여 사용자 메시지에서 핵심 정보를 추출합니다.
        # TODO: AI 담당자는 이 부분을 실제 OpenAI API 호출 코드로 교체해야 합니다.
        # 예시: "제 이름은 홍길동입니다." -> "홍길동"
        # 지금은 임시로 사용자 메시지 전체를 값으로 사용합니다.
        extracted_value = user_message 
        
        # 4. DB의 계약서 내용을 업데이트합니다.
        await crud.update_contract_content(db, contract, current_question_item["field_id"], extracted_value)
        updated_field_info = schemas.UpdatedField(field_id=current_question_item["field_id"], value=extracted_value)

    # 5. DB 업데이트 후의 최신 계약서 내용을 다시 가져옵니다.
    final_contract = await crud.get_contract_by_id(db, contract.id, contract.owner_id)
    final_content = final_contract.content or {}

    # 6. 다음 질문을 찾거나, 모든 질문이 완료되었는지 확인합니다.
    next_question = None
    for item in scenario:
        if item["field_id"] not in final_content:
            next_question = item["question"]
            break

    is_finished = next_question is None
    if is_finished:
        reply_message = "모든 항목이 작성되었습니다. 계약서 작성을 완료합니다. 마이페이지에서 다운로드할 수 있습니다."
    else:
        reply_message = next_question

    # 7. 최종 응답을 프론트엔드에 보낼 형태로 구성합니다.
    return schemas.ChatResponse(
        reply=reply_message,
        updated_field=updated_field_info,
        is_finished=is_finished,
        full_contract_data=final_content
    )

def create_docx_from_contract(contract: models.Contract):
    """
    DB에 저장된 계약서 정보로 .docx (워드) 문서를 생성합니다.
    """
    document = Document()
    document.add_heading(f'{contract.contract_type}', level=1)
    
    content = contract.content or {}
    
    # TODO: 프론트엔드와 약속된 field_id를 "임차인 성명" 과 같이
    # 실제 계약서에 들어갈 보기 좋은 한글 레이블로 변환하는 로직이 필요합니다.
    field_id_to_label = {
        "lessee_name": "임차인 성명",
        "property_address": "부동산 소재지",
        "deposit_amount": "보증금",
        "rent_amount": "월 차임"
        # ... 모든 필드에 대한 매핑 추가 ...
    }
    
    for field_id, value in content.items():
        label = field_id_to_label.get(field_id, field_id) # 한글 레이블이 없으면 원래 id 사용
        document.add_paragraph(f"{label}: {value}")
        
    return document

