import os
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from docx import Document

from . import crud, models, schemas

# .env에 추가한 API키를 사용하도록 설정
client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# 계약서 종류별로 필요한 필드와 질문 순서를 정의합니다.
# 프론트엔드와 이 field_id를 기준으로 화면을 업데이트하기로 약속해야 합니다.
CONTRACT_SCENARIOS = {
    "근로계약서": [
    # 1. 당사자 정보 (근로계약의 주체)
    {"field_id": "employer_name", "question": "먼저, 계약을 체결하는 고용주(대표자)의 성함은 무엇인가요?"},
    {"field_id": "business_name", "question": "고용주가 운영하는 사업체명(회사 이름)을 알려주세요."},
    {"field_id": "business_phone", "question": "사업체의 대표 연락처(전화번호)를 입력해주세요."},
    {"field_id": "business_address", "question": "사업장의 소재지(주소)는 어디인가요?"},

    {"field_id": "employee_name", "question": "이제 근로자(본인)의 성함은 무엇인가요?"},
    {"field_id": "employee_resident_number", "question": "근로자의 주민등록번호를 알려주세요."},
    {"field_id": "employee_address", "question": "근로자의 현 주소는 어디인가요?"},
    {"field_id": "employee_phone", "question": "근로자의 연락처(전화번호)를 입력해주세요."},

    # 2. 근로계약 기간 및 장소 (계약의 범위)
    {"field_id": "contract_date", "question": "이 근로계약서를 최종적으로 계약한 날짜(작성일)는 언제인가요?"},
    {"field_id": "start_date", "question": "실제 근로를 시작하는 날(근로개시일)은 언제인가요(예: 2025년 1월 1일)?"},
    {"field_id": "end_date", "question": "근로 종료일이 정해져 있다면 언제인가요? (정규직이거나 기간이 정해지지 않았다면 '기간 없음'이라고 답해주세요.)"},
    {"field_id": "work_location", "question": "근무하게 될 실제 장소(근무장소)를 알려주세요."},
    {"field_id": "job_description", "question": "근로자가 수행할 업무 내용(직종)은 무엇인가요?"},

    # 3. 근로시간 및 휴게시간
    {"field_id": "work_day", "question": "일주일에 몇 요일(예: 월요일부터 금요일까지)을 근무하나요?"},
    {"field_id": "start_time", "question": "하루 근로를 시작하는 소정근로시간(시작 시간)을 알려주세요."},
    {"field_id": "end_time", "question": "하루 근로를 마치는 소정근로시간(종료 시간)을 알려주세요."},
    {"field_id": "rest_time", "question": "하루 중 주어지는 휴게시간은 총 몇 분인가요?"},

    # 4. 임금 (급여)
    {"field_id": "salary_amount", "question": "월 지급되는 총 임금(월 급여)은 얼마인가요?"},
    {"field_id": "hourly_wage", "question": "시급 또는 일급이 별도로 있다면 얼마인가요? (없다면 '없음'이라고 답해주세요.)"},
    {"field_id": "bonus_amount", "question": "별도로 지급되는 상여금이 있다면 얼마인가요? (없다면 '없음'이라고 답해주세요.)"},
    {"field_id": "salary_payment_date", "question": "임금은 매월 며칠에 지급되나요?"},
    {"field_id": "payment_method", "question": "임금 지급 방법은 근로자 명의 계좌이체인가요, 아니면 직접 현금 지급인가요?"}
    
    # 이 외에 연차유급휴가, 사회보험 등의 질문을 추가할 수 있습니다.
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
    scenario = CONTRACT_SCENARIOS.get(contract.contract_type, [])
    current_content = contract.content or {}
    
    # merge test
    # 1. 현재 계약서의 시나리오와 진행 상태를 파악합니다.
    # scenario = CONTRACT_SCENARIOS.get(contract.contract_type, [])
    # current_content = contract.content or {}
    
    # 2. 현재 답변이 어떤 질문에 대한 것인지 찾습니다.
    current_question_item = None
    for item in scenario:
        if item["field_id"] not in current_content:
            current_question_item = item
            break

    updated_field_info = None
    if current_question_item:
        # --- ❗️❗️❗️ 핵심 수정 부분 시작 ❗️❗️❗️ ---
        
        # 3. AI(GPT)를 호출하여 사용자 메시지에서 핵심 정보를 추출합니다.
        #    "제 이름은 홍길동입니다." -> "홍길동"
        try:
            # GPT에게 역할과 목표를 부여하는 프롬프트(Prompt)
            system_prompt = (
                "You are a helpful assistant that extracts key information from a user's sentence. "
                "The user will provide an answer to a question. "
                f"The question is: '{current_question_item['question']}'. "
                "Please extract only the essential value from the user's answer. "
                "For example, if the user says 'My name is John Doe', you should only return 'John Doe'. "
                "If the user says 'I work 50 hours a week', you should only return '50 hours'."
            )
            
            # OpenAI API 호출
            response = await client.chat.completions.create(
                model="gpt-4o",  # 또는 "gpt-3.5-turbo"
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0, # 일관된 답변을 위해 0으로 설정
            )
            extracted_value = response.choices[0].message.content.strip()

        except Exception as e:
            # API 호출 실패 시, 임시로 사용자 메시지 전체를 사용하고 에러 로그를 남깁니다.
            print(f"OpenAI API call failed: {e}")
            extracted_value = user_message
        
        # --- 핵심 수정 부분 끝 ---
        
        # 4. DB의 계약서 내용을 업데이트합니다.
        contract = await crud.update_contract_content(db, contract, current_question_item["field_id"], extracted_value)
        updated_field_info = schemas.UpdatedField(field_id=current_question_item["field_id"], value=extracted_value)

    # 5. DB 업데이트 후의 최신 계약서 내용을 다시 가져옵니다. (crud 함수가 업데이트된 객체를 반환하도록 수정했다면 이 부분은 필요 없습니다)
    final_content = contract.content or {}

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
