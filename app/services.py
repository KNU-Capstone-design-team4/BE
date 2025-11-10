import os
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from docx import Document
from docxtpl import DocxTemplate
import numpy as np
import asyncio  # 1. (추가) RAG용
import numpy as np  # 2. (추가) RAG용
from dotenv import load_dotenv  # 3. (추가) RAG용
from typing import List, Dict, Optional # 4. (추가) 타입 힌트

from . import crud, models, schemas

load_dotenv()
# .env에 추가한 API키를 사용하도록 설정
client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# RAG용 지식 베이스 (TIP_LIST)
TIP_LIST = [
    "1.**(초과근무 합의)** 법정근로시간(주 40시간)을 초과하여 근무하려면, 반드시 근로자와의 서면 합의가 필요합니다. 구두 합의는 추후 분쟁의 소지가 될 수 있습니다.",
    "2.** (청소년 근로)** 만 18세 미만 청소년의 법정근로시간은 하루 7시간, 주 35시간을 초과할 수 없으며, 본인이 동의해도 연장근로는 주 5시간까지만 가능합니다.",
    "3.** (휴일근로수당)** 휴일에 근무했다면 반드시 가산수당을 받아야 합니다. 8시간 이내 근무는 통상임금의 1.5배, 8시간을 초과한 근무는 2배를 지급받아야 합니다.",
    "4.** (야간근로수당)** 오후 10시부터 다음 날 오전 6시 사이에 근무했다면, 통상임금의 50%를 야간근로수당으로 추가 지급받아야 합니다.",
    "5.** (수당 중복지급)** 만약 휴일에 야간 근무를 했다면, 휴일근로수당(1.5배)과 야간근로수당(0.5배)이 중복으로 적용되어 통상임금의 2배를 받을 수 있습니다.",
    "6.** (주휴수당 조건)** 주휴수당은 '1주 소정근로시간 15시간 이상'과 '1주 개근'이라는 두 가지 조건을 모두 충족해야 발생합니다.",
    "7. (단기 근로자 주휴수당) 계약 기간이 1주일이라도, 주 15시간 이상 일하고 개근했다면 계약 종료와 별개로 주휴수당을 지급받을 수 있습니다. 다음 주 근무 여부는 상관없습니다.",
    "8.** (계약서 작성 시점)** 모든 근로계약서는 반드시 업무를 시작하기 전에 작성해야 하며, 작성 후 1부를 근로자에게 즉시 교부하는 것이 법적 의무입니다.",
    "9.** (계약서 미작성 벌금)** 근로계약서를 서면으로 작성하고 교부하지 않은 경우, 사업주는 500만원 이하의 벌금에 처해질 수 있습니다.",
    "10.** (근로조건 변경)** 임금, 근로시간 등 중요한 근로조건이 변경될 경우, 구두 합의만으로는 부족하며 반드시 변경된 내용을 서면으로 명시하여 다시 교부해야 합니다.",
    "11.** (단시간 근로자 계약서)** 아르바이트처럼 근무 요일이나 시간이 유동적인 경우, \"월, 수, 금, 14:00~18:00\"와 같이 근로일과 근로일별 근로시간을 반드시 구체적으로 명시해야 합니다.",
    "12.** (휴게시간 명시)** 휴게시간은 임금에 포함되지 않는 무급 시간이 원칙입니다. 따라서 계약서에 휴게시간을 명확히 기재해야 총 근로시간 및 임금 계산에 대한 오해를 막을 수 있습니다.",
    "13.** (휴게시간 법적 기준)** 근로시간이 4시간이면 30분 이상, 8시간이면 1시간 이상의 휴게시간을 '근로시간 도중에' 부여해야 합니다. 업무 시작 전이나 종료 후에 부여하는 것은 위법입니다.",
    "14.** (퇴직금 연봉 포함 금지)** 월급이나 연봉에 퇴직금을 포함하여 지급하는 계약은 근로기준법상 불법이며 무효입니다. 퇴직금은 반드시 퇴직 시점에 별도로 정산받아야 합니다.",
    "15.** (포괄임금제 유의사항)** 연장·야간수당 등을 미리 월급에 포함하는 포괄임금제 계약은 가능하지만, 실제 발생한 수당이 약정된 수당보다 많을 경우 차액을 추가로 지급해야 합니다.",
    "16.** (공휴일 유급휴일)** 2022년부터 사업장 규모와 상관없이 모든 근로자는 '빨간 날'(관공서 공휴일)을 유급휴일로 보장받아야 합니다.",
    "17.** (대체휴일 적용)** 공휴일이 주말과 겹치는 경우 발생하는 대체공휴일 역시 모든 사업장에서 유급휴일로 보장해야 합니다.",
    "18.** (휴일 조항 명시)** 근로계약서에는 '주휴일'이 무슨 요일인지, '공휴일'을 유급으로 보장하는지 등 휴일에 관한 사항을 반드시 포함해야 합니다.",
    "19.** (5인 미만 사업장 예외)** 연장·야간·휴일근로 가산수당, 연차유급휴가 등의 일부 규정은 상시 근로자 5인 미만 사업장에는 적용되지 않을 수 있으니 확인이 필요합니다.",
    "20.** (벌금과 별개로 임금 지급 의무)** 사업주가 근로기준법 위반으로 벌금을 내더라도, 근로자에게 지급해야 할 주휴수당, 가산수당 등의 임금 지급 의무는 사라지지 않습니다.",
    "21.**(최저시급)2025년을 기준으로 최저시급은 10030원입니다. 이를 지키지 않을 경우, 5년 이하의 징역에 처할 수 있습니다."
]
# RAG 임계값
SIMILARITY_THRESHOLD = 0.4

# 전역 변수로 임베딩과 잠금 관리
tip_embeddings: List[np.ndarray] = []
tip_embeddings_lock = asyncio.Lock()
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

async def get_tip_embeddings():
    """팁 목록 임베딩을 (최초 1회) 생성하고 캐시합니다."""
    global tip_embeddings
    async with tip_embeddings_lock:
        if not tip_embeddings:
            print("RAG 팁 목록 임베딩을 생성합니다...")
            embeddings_response = await client.embeddings.create(
                model="text-embedding-3-small",
                input=TIP_LIST
            )
            tip_embeddings = [np.array(data.embedding) for data in embeddings_response.data]
            print("RAG 임베딩 생성 완료!")
    return tip_embeddings

async def get_embedding(text: str) -> np.ndarray:
    """단일 텍스트의 임베딩을 반환합니다."""
    response = await client.embeddings.create(model="text-embedding-3-small", input=text)
    return np.array(response.data[0].embedding)

async def find_top_relevant_tips(question: str, top_n=3):
    """(RAG) 질문과 가장 관련성 높은 팁과 최고 점수를 반환합니다."""
    embeddings = await get_tip_embeddings()
    question_embedding = await get_embedding(question)
    similarities = [np.dot(question_embedding, tip_embedding) for tip_embedding in embeddings]
    
    top_indices = np.argsort(similarities)[-top_n:][::-1]
    top_score = similarities[top_indices[0]] if top_indices.size > 0 else 0.0
    relevant_tips_str = "\n\n".join([TIP_LIST[i] for i in top_indices])
    
    return relevant_tips_str, top_score

async def get_rag_response(question: str, relevant_tips: str) -> str:
    """(RAG) CoT 프롬프트를 사용해 법률 질문에 대한 답변을 생성합니다."""
    system_prompt = f"""
    당신은 주어진 '참고 자료'만을 기반으로 답변하는 AI 노무사입니다. 다음 규칙을 엄격히 따르세요.

    --- 참고 자료 ---
    {relevant_tips}
    -----------------

    [규칙]
    1.  [생각 단계]: 먼저 사용자의 질문을 분석하고, '참고 자료'에서 관련된 모든 조항을 찾습니다.
    2.  [답변 생성 단계]: '생각 단계'의 논리를 바탕으로, 사용자에게 최종적인 답변을 친절하고 명확하게 생성합니다.
    3.  [출처 명시 단계]: 답변 내용의 근거가 된 '참고 자료'의 '팁 번호'를 문장 끝에 (출처: 팁 N번) 형식으로 반드시 포함합니다.
    
    (주의: 이 프롬프트는 '다음 질문 제안'을 제거하여, 법률 답변만 깔끔하게 반환합니다.)
    """
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": question}],
        temperature=0,
    )
    return response.choices[0].message.content.strip()

async def extract_value_from_answer(user_message: str, question: str) -> str:
    """(Form-Filling) 사용자의 답변에서 핵심 값만 추출합니다."""
    try:
        system_prompt = (
            "You are a helpful assistant that extracts key information from a user's sentence. "
            f"The question is: '{question}'. "
            "Please extract only the essential value from the user's answer. "
            "For example, if the user says 'My name is John Doe', you should only return 'John Doe'."
        )
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"OpenAI (extract_value) API call failed: {e}")
        return user_message  # 실패 시 원본 메시지 반환
    
'''async def process_chat_message(db: AsyncSession, contract: models.Contract, user_message: str):
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
    )'''

# ❗️ GET API에서도 사용할 수 있도록 "다음 질문" 찾는 로직을 별도 함수로 분리
def find_next_question(contract: models.Contract) -> Optional[str]:
    """
    계약서 객체를 받아, 다음에 물어볼 질문 텍스트를 반환합니다.
    (질문이 모두 완료되었으면 None을 반환)
    """
    scenario = CONTRACT_SCENARIOS.get(contract.contract_type, [])
    current_content = contract.content or {}
    
    for item in scenario:
        if item["field_id"] not in current_content:
            return item["question"]  # 👈 다음에 물어볼 질문 텍스트
    
    return None  # 👈 모든 질문이 완료됨

async def process_chat_message(db: AsyncSession, contract: models.Contract, user_message: str) -> schemas.ChatResponse:
    """
    [하이브리드 챗봇]
    사용자 메시지를 받아서 '시작 신호', '법률 질문', '폼 답변'인지 판별하고 처리합니다.
    """
    
    # --- 1. 현재 폼 작성 상태 파악 (먼저 수행) ---
    scenario = CONTRACT_SCENARIOS.get(contract.contract_type, [])
    current_content = contract.content or {}
    
    # 현재 답변을 기다리는 질문 항목 찾기
    current_question_item: Optional[Dict] = None
    for item in scenario:
        if item["field_id"] not in current_content:
            current_question_item = item
            break

    # --- 2. (신규) "시작/재개 신호" 처리 ---
    # 사용자가 빈 메시지를 보낸 경우 (Swagger에서 Execute 누른 경우)
    # RAG나 값 추출을 하지 않고, 현재 질문을 즉시 반환합니다.
    if user_message.strip() == "" or user_message.strip() == "string":
        reply_message: str
        is_finished: bool
        
        if current_question_item:
            # 폼 작성이 진행 중 -> 현재 질문을 반환 (이것이 첫 번째 질문이 됨)
            reply_message = current_question_item['question']
            is_finished = False
        else:
            # 폼 작성이 이미 완료된 경우
            reply_message = "모든 항목이 작성되었습니다. 계약서 다운로드를 진행하시거나, 법률 관련 팁이 궁금하시면 질문해주세요."
            is_finished = True
        
        return schemas.ChatResponse(
            reply=reply_message,
            updated_field=None,  # 아무것도 업데이트되지 않음
            is_finished=is_finished,
            full_contract_data=current_content
        )

    # --- 3. 입력 분류: 법률 질문(RAG)인지 폼 답변인지 판별 ---
    # (user_message가 비어있지 않은 경우에만 실행)
    relevant_tips, top_score = await find_top_relevant_tips(user_message)
    is_legal_question = top_score >= SIMILARITY_THRESHOLD

    # --- 4. 로직 분기 ---

    if is_legal_question:
        # --- [분기 A] 법률 질문(RAG)으로 판별된 경우 ---
        
        # 4-A-1. RAG 답변 생성
        rag_answer = await get_rag_response(user_message, relevant_tips)
        
        # 4-A-2. 폼 작성으로 복귀하기 위한 '재질문' 준비
        if current_question_item:
            re_ask_prompt = f"\n\n[이어서 진행]\n{current_question_item['question']}"
            is_finished = False
        else:
            re_ask_prompt = "\n\n(계약서 작성은 완료된 상태입니다. 추가로 궁금한 점이 있으신가요?)"
            is_finished = True
            
        final_reply = rag_answer + re_ask_prompt

        # 4-A-3. RAG 질문은 폼을 업데이트하지 않음
        return schemas.ChatResponse(
            reply=final_reply,
            updated_field=None, 
            is_finished=is_finished,
            full_contract_data=current_content
        )

    else:
        # --- [분기 B] 폼 답변으로 판별된 경우 ---

        # 4-B-1. (예외 처리) 폼이 이미 끝났는데 RAG도 아닌 경우
        # (이론상 2번 로직에서 처리되지만, 안전장치로 둠)
        if not current_question_item:
            reply = "모든 항목이 작성되었습니다. 계약서 다운로드를 진행하시거나, 법률 관련 팁이 궁금하시면 질문해주세요."
            return schemas.ChatResponse(
                reply=reply, updated_field=None, is_finished=True, full_contract_data=current_content
            )

        # 4-B-2. (정상) 폼 답변에서 값 추출 및 DB 업데이트
        extracted_value = await extract_value_from_answer(user_message, current_question_item['question'])
        contract = await crud.update_contract_content(db, contract, current_question_item["field_id"], extracted_value)
        updated_field_info = schemas.UpdatedField(field_id=current_question_item["field_id"], value=extracted_value)
        
        new_content = contract.content or {} # 업데이트된 최신 content

        # 4-B-3. 다음 질문 찾기
        next_question_item: Optional[Dict] = None
        for item in scenario:
            if item["field_id"] not in new_content:
                next_question_item = item
                break
        
        # 4-B-4. 다음 질문 또는 완료 메시지 반환
        if next_question_item:
            reply = next_question_item['question']
            is_finished = False
        else:
            reply = "모든 항목이 작성되었습니다. 계약서 작성을 완료합니다. 마이페이지에서 다운로드할 수 있습니다."
            is_finished = True
            
        return schemas.ChatResponse(
            reply=reply,
            updated_field=updated_field_info,
            is_finished=is_finished,
            full_contract_data=new_content
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