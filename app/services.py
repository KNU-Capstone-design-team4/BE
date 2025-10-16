import os
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from docx import Document
from docxtpl import DocxTemplate

from . import crud, models, schemas

# .env에 추가한 API키를 사용하도록 설정
client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


# 계약서 종류별로 필요한 필드와 질문 순서를 정의합니다.
# (기존 CONTRACT_SCENARIOS는 그대로 유지)
CONTRACT_SCENARIOS = {
    "근로계약서":[
        {"field_id": "employer_name", "question": "먼저, 계약을 체결하는 고용주(대표자)의 성함은 무엇인가요? (예: 김철수)"},
        {"field_id": "business_name", "question": "고용주가 운영하는 사업체명(회사 이름)을 알려주세요. (예: (주)한빛유통)"},
        {"field_id": "business_phone", "question": "사업체의 대표 연락처(전화번호)를 입력해주세요. (예: 02-1234-5678)"},
        {"field_id": "business_address", "question": "사업장의 소재지(주소)는 어디인가요? (예: 서울시 강남구 테헤란로 123)"},
        {"field_id": "employee_name", "question": "이제 근로자(본인)의 성함은 무엇인가요? (예: 이영희)"},
        {"field_id": "employee_address", "question": "근로자의 현 주소는 어디인가요? (예: 경기도 성남시 분당구 정자일로 123)"},
        {"field_id": "employee_phone", "question": "근로자의 연락처(전화번호)를 입력해주세요. (예: 010-9876-5432)"},
        {"field_id": "contract_date", "question": "이 근로계약서를 최종적으로 작성한 날짜(계약일)는 언제인가요? (예: 2025년 10월 16일)"},
        {"field_id": "start_year", "question": "실제 근로를 시작하는 날(근로개시일)의 '년도'를 숫자로 알려주세요. (예: 2025)"},
        {"field_id": "start_month", "question": "실제 근로를 시작하는 날(근로개시일)의 '월'을 숫자로 알려주세요. (예: 1)"},
        {"field_id": "start_date", "question": "실제 근로를 시작하는 날(근로개시일)의 '일'을 숫자로 알려주세요. (예: 1)"},
        {"field_id": "work_location", "question": "근무하게 될 실제 장소(근무장소)를 알려주세요. (예: 사업장과 동일)"},
        {"field_id": "job_description", "question": "근로자가 수행할 업무 내용(직종)은 무엇인가요? (예: 사무 보조 및 서류 정리)"},
        {"field_id": "work_day_count", "question": "일주일에 '총 몇 일'을 근무하나요? (숫자만 입력, 예: 5)"},
        {"field_id": "work_day_description", "question": "실제 근무 요일을 명시해주세요. (예: 월요일부터 금요일까지)"},
        {"field_id": "start_time", "question": "하루 근로를 시작하는 시간(시작 시간)을 알려주세요. (예: 09:00)"},
        {"field_id": "end_time", "question": "하루 근로를 마치는 시간(종료 시간)을 알려주세요. (예: 18:00)"},
        {"field_id": "rest_time", "question": "하루 중 주어지는 휴게시간은 총 몇 분인가요? (숫자만 입력, 예: 60)"},
        {"field_id": "is_eligible_for_weekly_holiday", "question": "주 15시간 이상 근무하여 법적으로 주휴수당 지급 대상에 해당하나요? (예: 네/아니오)"},
        {"field_id": "Weekly_Paid_Holiday", "question": "주휴일(유급휴일)로 지정된 요일은 무엇인가요? (지급 대상이 아닐 경우 'X'를 기재)"},
        {"field_id": "salary_payment_cycle", "question": "임금의 계산 단위는 월급, 일급, 시급 중 무엇인가요? (예: 월급)"},
        {"field_id": "salary_amount", "question": "월(일, 시간) 지급되는 총 임금액을 숫자로만 알려주세요. (예: 2500000)"},
        {"field_id": "is_bonus_paid", "question": "별도로 정기적인 상여금이 지급되나요? (예: 있음/없음)"},
        {"field_id": "bonus_amount", "question": "상여금이 있다면 그 금액은 얼마인가요? (없다면 '0' 기재)"},
        {"field_id": "is_allowance_paid", "question": "상여금 외 기타 급여(제수당 등)가 지급되나요? (예: 있음/없음)"},
        {"field_id": "allowance_details", "question": "기타 급여가 있다면 종류와 금액을 상세히 알려주세요. (예: 식대 10만원, 교통비 5만원 / 없다면 '없음' 기재)"},
        {"field_id": "salary_payment_date", "question": "임금은 매월 며칠에 지급되나요? (숫자만 입력, 예: 25)"},
        {"field_id": "payment_method_type", "question": "임금 지급 방법은 '계좌이체'인가요, '직접 현금 지급'인가요?"},
        {"field_id": "apply_employment_insurance", "question": "고용보험 적용 여부를 '체크' 또는 '미체크'로 알려주세요."},
        {"field_id": "apply_industrial_accident_insurance", "question": "산재보험 적용 여부를 '체크' 또는 '미체크'로 알려주세요."},
        {"field_id": "apply_national_pension", "question": "국민연금 적용 여부를 '체크' 또는 '미체크'로 알려주세요."},
        {"field_id": "apply_health_insurance", "question": "건강보험 적용 여부를 '체크' 또는 '미체크'로 알려주세요."}
  ],
    "임대차계약서": [
        {"field_id": "lessee_name", "question": "안녕하세요! 계약서 작성을 시작하겠습니다. 임차인의 성함은 무엇인가요?"},
        {"field_id": "property_address", "question": "계약할 부동산의 정확한 주소는 어디인가요?"},
        {"field_id": "deposit_amount", "question": "보증금은 얼마인가요?"},
        {"field_id": "rent_amount", "question": "월 차임(월세)은 얼마인가요?"},
        # ... 추가 질문들 ...
    ]
}

# ⭐️ 1. 개선된 Few-Shot 프롬프트 템플릿 정의
FEW_SHOT_PROMPT_TEMPLATE = """
# ROLE (역할)
You are an expert assistant specializing in extracting only the essential, core information from a user's answer related to a legal contract.

# INSTRUCTION (지시사항)
- Your mission is to extract the single, most important value from the user's sentence in response to the question provided.
- NEVER add any additional explanations, greetings, or introductory phrases like "The extracted value is:".
- If the user's answer is a number, extract only the number.
- If the user's answer is a name or place, extract only that name or place.
- If the answer is a date, extract the date expression as is.
- Respond with ONLY the extracted value and nothing else.

# EXAMPLES (예시)

---
[Question]: 먼저, 계약을 체결하는 고용주(대표자)의 성함은 무엇인가요? (예: 김철수)
[User's Answer]: 안녕하세요, 대표님 성함은 김철수입니다.
[Your Answer]: 김철수
---
[Question]: 사업장의 소재지(주소)는 어디인가요? (예: 서울시 강남구 테헤란로 123)
[User's Answer]: 저희 회사는 서울시 강남구 테헤란로 123에 위치하고 있습니다.
[Your Answer]: 서울시 강남구 테헤란로 123
---
[Question]: 하루 중 주어지는 휴게시간은 총 몇 분인가요? (숫자만 입력, 예: 60)
[User's Answer]: 휴게시간은 60분으로 정해져 있어요.
[Your Answer]: 60
---
[Question]: 임금은 매월 며칠에 지급되나요? (숫자만 입력, 예: 25)
[User's Answer]: 25일입니다.
[Your Answer]: 25
---
[Question]: 이 근로계약서를 최종적으로 작성한 날짜(계약일)는 언제인가요? (예: 2025년 10월 16일)
[User's Answer]: 2025년 10월 16일에 작성했습니다.
[Your Answer]: 2025년 10월 16일
---
"""

async def process_chat_message(db: AsyncSession, contract: models.Contract, user_message: str):
    """
    사용자 메시지를 처리하고, 계약서를 업데이트하며, 다음 챗봇 응답을 생성합니다.
    """
    scenario = CONTRACT_SCENARIOS.get(contract.contract_type, [])
    current_content = contract.content or {}
    
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

            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "user", "content": final_prompt},
                ],
                temperature=0,
                stop=["---"] # 예시와 실제 답변을 구분하는 '---'가 나오면 생성을 중단시켜 안정성을 높입니다.
            )
            ######## zero shot프롬프트 

            '''####### few shot프롬프트
            messages_list = [
                {"role": "system", "content": system_prompt},
            ]

            # 2. Few-Shot 예시 (모범 답안)을 추가합니다.
            # list.extend() 또는 '+' 연산자로 리스트를 합칩니다.
            messages_list.extend(FEWSHOT_EXAMPLES)

            # 3. 실제 사용자 질문을 마지막에 추가합니다.
            messages_list.append({"role": "user", "content": user_message})


            # 4. API 호출 시 최종 리스트를 사용합니다.
            response = await client.chat.completions.create(
                model="gpt-4o",  
                # 🌟 Few-Shot 예시가 포함된 messages_list를 전달 🌟
                messages=messages_list, 
                temperature=0, 
            )
            ####### few shot프롬프트 '''

            extracted_value = response.choices[0].message.content.strip()

        except Exception as e:
            print(f"OpenAI API call failed: {e}")
            extracted_value = user_message
        
        contract = await crud.update_contract_content(db, contract, current_question_item["field_id"], extracted_value)
        updated_field_info = schemas.UpdatedField(field_id=current_question_item["field_id"], value=extracted_value)

    final_content = contract.content or {}

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
    current_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(current_dir, "..", "templates", "working.docx")
    print(f"DEBUG: 시도 경로: {template_path}")
    
    try:
        doc = DocxTemplate(template_path)
    except Exception as e:
        raise FileNotFoundError(f"템플릿 파일을 찾을 수 없습니다: {template_path}. 경로를 확인해주세요. 오류: {e}")

    context = contract.content or {} 
    doc.render(context)
    return doc