import os
import json
import uuid
import datetime
import numpy as np
import asyncio
from typing import Dict, Optional, Any, Tuple, List
from openai import AsyncOpenAI
from docxtpl import DocxTemplate
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas

client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# --- 1. 근로계약서 전용 시나리오 ---
CONTRACT_SCENARIO = [
    # 1. 당사자 정보
    {"field_id": "employer_name", "question": "먼저, 계약을 체결하는 고용주(대표자)의 성함은 무엇인가요? (예: 김철수)"},
    {"field_id": "business_name", "question": "고용주가 운영하는 사업체명(회사 이름)을 알려주세요. (예: (주)한빛유통)"},
    {"field_id": "business_phone", "question": "사업체의 대표 연락처(전화번호)를 입력해주세요."},
    {"field_id": "business_address", "question": "사업장의 소재지(주소)는 어디인가요?"},
    {"field_id": "employee_name", "question": "이제 근로자(본인)의 성함은 무엇인가요?"},
    {"field_id": "employee_address", "question": "근로자의 현 주소는 어디인가요?"},
    {"field_id": "employee_phone", "question": "근로자의 연락처(전화번호)를 입력해주세요."},

    # 2. 계약 기간 및 장소
    {"field_id": "start_date_full", "question": "실제 근로를 시작하는 날(근로개시일)은 언제인가요? (예: 2025년 11월 1일)"},
    {"field_id": "work_location", "question": "근무하게 될 실제 장소(근무장소)를 알려주세요. (예: 사업장과 동일)"},
    {"field_id": "job_description", "question": "근로자가 수행할 업무 내용(직종)은 무엇인가요? (예: 사무 보조 및 서류 정리)"},

    # 3. 근로시간 및 휴일
    {"field_id": "start_time", "question": "하루 근로를 시작하는 시간(시업 시간)을 알려주세요. (예: 09:00)"},
    {"field_id": "end_time", "question": "하루 근로를 마치는 시간(종업 시간)을 알려주세요. (예: 18:00)"},
    {"field_id": "rest_time", "question": "하루 중 주어지는 휴게시간은 총 몇 분인가요? (숫자만 입력, 예: 60)"},
    {"field_id": "work_day", "question": "일주일에 '총 몇 일'을 근무하나요? (숫자만 입력, 예: 5)"},
    {"field_id": "Weekly_Paid_Holiday", "question": "주휴일(유급휴일)로 지정된 요일은 무엇인가요? (예: 매주 일요일)"},

    # 4. 임금 (급여)
    {"field_id": "salary_amount", "question": "월(일, 시간)급 총 임금액을 숫자로만 알려주세요. (예: 2500000)"},
    {"field_id": "is_bonus_paid", "question": "별도로 정기적인 상여금이 지급되나요? (예: 있음/없음)"},
    {"field_id": "bonus_amount", "question": "상여금액은 얼마인가요?"}, 
    {"field_id": "is_allowance_paid", "question": "상여금 외 기타 급여(제수당 등)가 지급되나요? (예: 있음/없음)"},
    {"field_id": "allowance_details", "question": "기타 급여가 있다면 종류와 금액을 상세히 알려주세요. (예: 식대 10만원)"}, 
    {"field_id": "salary_payment_date", "question": "임금은 매월 며칠에 지급되나요? (숫자만 입력, 예: 25)"},
    {"field_id": "payment_method_type", "question": "임금 지급 방법은 '계좌이체'인가요, '직접 현금 지급'인가요?"},
    
    # 5. 사회보험 및 기타
    {"field_id": "apply_employment_insurance", "question": "고용보험에 가입하나요? (예: 예/아니오)"},
    {"field_id": "apply_industrial_accident_insurance", "question": "산재보험에 가입하나요? (예: 예/아니오)"},
    {"field_id": "apply_national_pension", "question": "국민연금에 가입하나요? (예: 예/아니오)"},
    {"field_id": "apply_health_insurance", "question": "건강보험에 가입하나요? (예: 예/아니오)"},
    {"field_id": "contract_date_full", "question": "이 근로계약서를 최종적으로 작성한 날짜(계약일)는 언제인가요? (예: 오늘)"},
]

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

# ⭐️ 1. 개선된 Few-Shot 프롬프트 템플릿 정의
SMART_EXTRACTION_PROMPT_TEMPLATE = """
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

SIMILARITY_THRESHOLD = 0.4

tip_embeddings: List[np.ndarray] = []
tip_embeddings_lock = asyncio.Lock()

async def get_tip_embeddings():
    global tip_embeddings
    async with tip_embeddings_lock:
        if not tip_embeddings:
            resp = await client.embeddings.create(
                model="text-embedding-3-small",
                input=TIP_LIST
            )
            tip_embeddings = [np.array(d.embedding) for d in resp.data]
    return tip_embeddings

async def get_embedding(text: str):
    resp = await client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return np.array(resp.data[0].embedding)

async def find_top_relevant_tips(question: str, top_n=3):
    embeddings = await get_tip_embeddings()
    q_emb = await get_embedding(question)
    sims = [np.dot(q_emb, t) for t in embeddings]

    idx = np.argsort(sims)[-top_n:][::-1]
    top_score = sims[idx[0]]
    tips_str = "\n".join([TIP_LIST[i] for i in idx])
    return tips_str, top_score

async def get_rag_response(question: str, relevant_tips: str) -> str:
    system_prompt = f"""
당신은 근로기준 전문가입니다.
주어진 팁만을 기반으로 답변하세요.

--- 참고 자료 ---
{relevant_tips}
-----------------
"""
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": question}],
        temperature=0
    )
    return resp.choices[0].message.content.strip()

# --- 2. 근로계약서 전용 AI 추출기 ---
# (services.py의 get_smart_extraction_for_field 함수를 그대로 가져옴)
async def get_smart_extraction(
    client: AsyncOpenAI,
    field_id: str, 
    user_message: str, 
    question: str
) -> Dict:
    """
    [근로계약서 AI 스마트 추출기]
    (services.py에 있던 'get_smart_extraction_for_field'의 내용과 동일)
    """
    
    today = datetime.date.today()
    current_year = today.year
    json_format_example = '{"status": "...", "filled_fields": {"key": "value", ...}, "skip_next_n_questions": 0, "follow_up_question": null}'
    base_system_prompt = f"""
    당신은 사용자의 답변에서 핵심 정보를 추출하는 '스마트 폼 어시스턴트'입니다.
    오늘은 {today.strftime('%Y년 %m월 %d일')}입니다. (현재 연도는 {current_year}년)

    [규칙]
    1.  사용자의 답변(`user_message`)이 현재 질문(`question`)에 대해 충분하면, `status: "success"`를 반환합니다.
    2.  답변이 모호하거나 정보가 부족하면 `status: "clarify"`와 `follow_up_question`을 생성합니다.
    3.  `filled_fields`에는 템플릿(docxtpl)에 사용될 모든 변수를 채워야 합니다.
        - 괄호 ( ) 안을 채울 땐: "O" 또는 " " (공백)
        - 체크박스 ☐ 를 채울 땐: "☒" (U+2612) 또는 "☐" (U+2610)
        - 날짜 형식은 "YYYY년 MM월 DD일" (예: "2025년 03월 07일")
    4.  `skip_next_n_questions`는 '없음'을 선택하여 다음 질문이 불필요할 때 사용됩니다.
    5.  반드시 지정된 JSON 형식으로만 반환해야 합니다.

    [JSON 반환 형식]
    {json_format_example}
    """
    
    specific_examples = ""
    
    # [날짜] 예시 (start_date_full, contract_date_full)
    if field_id.endswith("_date_full"):
        specific_examples = f"""
        [예시 1: 날짜 (연도 모호)]
        question: "{question}"
        user_message: "5월 8일이요."
        AI: {{"status": "clarify", "filled_fields": {{}}, "skip_next_n_questions": 0, "follow_up_question": "네, 좋습니다. 몇 년도 5월 8일 말씀이신가요?"}}
        
        [예시 2: 날짜 (상대적 표현)]
        question: "{question}"
        user_message: "오늘이요."
        AI: {{"status": "success", "filled_fields": {{"{field_id}": "{today.strftime('%Y년 %m월 %d일')}"}}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 3: 날짜 (형식화)]
        question: "{question}"
        user_message: "2025년 3월 7일"
        AI: {{"status": "success", "filled_fields": {{"{field_id}": "2025년 03월 07일"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """
    
    # [상여금] 예시
    elif field_id == "is_bonus_paid":
        specific_examples = """
        [예시 1: '있음' 선택]
        question: "별도로 정기적인 상여금이 지급되나요? (예: 있음/없음)"
        user_message: "네 있어요"
        AI: {{"status": "success", "filled_fields": {{"is_bonus_paid_yes_o": "O", "is_bonus_paid_no_o": " "}}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 2: '없음' 선택 (다음 질문 스킵)]
        question: "별도로 정기적인 상여금이 지급되나요? (예: 있음/없음)"
        user_message: "아니요 없습니다"
        AI: {{"status": "success", "filled_fields": {{"is_bonus_paid_yes_o": " ", "is_bonus_paid_no_o": "O", "bonus_amount": "0"}}, "skip_next_n_questions": 1, "follow_up_question": null}}
        
        [예시 3: '있음'과 '금액'을 한 번에 답변]
        question: "별도로 정기적인 상여금이 지급되나요? (예: 있음/없음)"
        user_message: "네, 100만원이요."
        AI: {{"status": "success", "filled_fields": {{"is_bonus_paid_yes_o": "O", "is_bonus_paid_no_o": " ", "bonus_amount": "1,000,000"}}, "skip_next_n_questions": 1, "follow_up_question": null}}
        """

    # [기타급여] 예시
    elif field_id == "is_allowance_paid":
        specific_examples = """
        [예시 1: '있음' 선택]
        question: "상여금 외 기타 급여(제수당 등)가 지급되나요? (예: 있음/없음)"
        user_message: "네 있습니다"
        AI: {{"status": "success", "filled_fields": {{"is_allowance_paid_yes_o": "O", "is_allowance_paid_no_o": " "}}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 2: '있음'과 '내역'을 한 번에 답변]
        question: "상여금 외 기타 급여(제수당 등)가 지급되나요? (예: 있음/없음)"
        user_message: "네, 식대 10만원이요."
        AI: {{"status": "success", "filled_fields": {{"is_allowance_paid_yes_o": "O", "is_allowance_paid_no_o": " ", "allowance_details": "식대 10만원"}}, "skip_next_n_questions": 1, "follow_up_question": null}}

        [예시 3: '없음' 선택 (다음 질문 스킵)]
        question: "상여금 외 기타 급여(제수당 등)가 지급되나요? (예: 있음/없음)"
        user_message: "아니요 없어요"
        AI: {{"status": "success", "filled_fields": {{"is_allowance_paid_yes_o": " ", "is_allowance_paid_no_o": "O", "allowance_details": ""}}, "skip_next_n_questions": 1, "follow_up_question": null}}
        """

    # [지급방법] 예시
    elif field_id == "payment_method_type":
        specific_examples = """
        [예시 1: '계좌이체' 선택]
        question: "임금 지급 방법은 '계좌이체'인가요, '직접 현금 지급'인가요?"
        user_message: "통장으로 받을게요"
        AI: {{"status": "success", "filled_fields": {{"payment_method_direct_o": " ", "payment_method_bank_o": "O"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        ... (이하 지급방법 예시) ...
        """
    
    # [사회보험] 예시
    elif field_id.startswith("apply_"):
        check_variable_name = f"{field_id}_check" 
        specific_examples = f"""
        [예시 1: '예' 선택 (체크박스 ☒)]
        question: "{question}"
        user_message: "네 가입해요"
        AI: {{"status": "success", "filled_fields": {{"{check_variable_name}": "☑"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        
        [예시 2: '아니오' 선택 (체크박스 ☐)]
        question: "{question}"
        user_message: "아니요"
        AI: {{"status": "success", "filled_fields": {{"{check_variable_name}": "☐"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """
    
    # [기본] 예시
    else: 
        specific_examples = f"""
        [예시 1: 일반 텍스트 추출]
        question: "{question}"
        user_message: "저희 회사는 (주)한빛유통입니다."
        AI: {{"status": "success", "filled_fields": {{"{field_id}": "(주)한빛유통"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        ... (이하 기본 예시) ...
        """

    system_prompt_with_examples = f"{base_system_prompt}\n--- [필드별 퓨샷(Few-Shot) 예시] ---\n{specific_examples}"
    
    try:
        # (⭐️ 핵심 수정 3) 
        # 이 함수는 이제 인자로 받은 'client'를 사용하므로
        # API 키 인증이 완료된 상태로 AI와 통신합니다.
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt_with_examples},
                {"role": "user", "content": f"question: \"{question}\"\nuser_message: \"{user_message}\""},
            ],
            temperature=0.0,
            response_format={"type": "json_object"}, 
        )
        
        ai_response_str = response.choices[0].message.content
        ai_response_json = json.loads(ai_response_str)
        return ai_response_json
    except Exception as e:
        # (이제 이 예외 처리는 '인증 오류'가 아닌, 실제 AI의 타임아웃 등에서만 발생합니다)
        print(f"OpenAI (get_smart_extraction - labor_contract) API call failed: {e}")
        return {
            "status": "success", 
            "filled_fields": {field_id: user_message}, 
            "skip_next_n_questions": 0,
            "follow_up_question": None
        }

# --- 3. 근로계약서 전용 "다음 질문 찾기" 로직 ---
# (services.py의 process_chat_message 안에 있던 로직을 가져옴)
def find_next_question(
    current_content: Dict[str, Any]
) -> Tuple[Optional[Dict], int]:
    """
    현재 content를 기반으로 다음에 물어볼 질문(item)과 인덱스(index)를 반환합니다.
    """
    scenario = CONTRACT_SCENARIO
    
    current_question_item: Optional[Dict] = None
    current_question_index = -1 

    for i, item in enumerate(scenario):
        field_id = item["field_id"]
        
        # 기본 field_id가 채워졌는지 확인
        if field_id in current_content:
            continue
            
        # (특수 로직) 괄호나 체크박스 필드가 채워졌는지 확인
        if field_id == "is_bonus_paid" and "is_bonus_paid_yes_o" in current_content:
            continue
        if field_id == "is_allowance_paid" and "is_allowance_paid_yes_o" in current_content:
            continue
        if field_id == "payment_method_type" and "payment_method_direct_o" in current_content:
            continue
        if field_id.startswith("apply_") and f"{field_id}_check" in current_content:
            continue
            
        # 다음 질문 찾음
        current_question_index = i
        current_question_item = item
        break
    
    if current_question_item is None:
        current_question_index = len(scenario)

    return current_question_item, current_question_index

async def process_message(
    db: AsyncSession,
    contract,
    message: str
) -> schemas.ChatResponse:

    content = contract.content or {}

    # ✅ 1) 다음 질문 찾기
    current_item, current_index = find_next_question(content)

    # ✅ 2) 아무 입력 없으면 "시작/재개"
    if not message.strip():
        if current_item:
            return schemas.ChatResponse(
                reply=current_item["question"],
                updated_field=None,
                is_finished=False,
                full_contract_data=content
            )
        else:
            return schemas.ChatResponse(
                reply="모든 항목이 작성되었습니다! 추가 질문이 있나요?",
                updated_field=None,
                is_finished=True,
                full_contract_data=content
            )

    # ✅ 3) RAG 여부 판단
    tips, score = await find_top_relevant_tips(message)
    is_legal_question = score >= SIMILARITY_THRESHOLD

    if is_legal_question:
        rag = await get_rag_response(message, tips)

        follow = (
            f"\n\n이어서 진행합니다.\n{current_item['question']}"
            if current_item else "\n\n계약서 작성을 모두 완료했습니다."
        )

        return schemas.ChatResponse(
            reply=rag + follow,
            updated_field=None,
            is_finished=(current_item is None),
            full_contract_data=content
        )

    # ✅ 4) 폼 답변 처리
    if not current_item:
        return schemas.ChatResponse(
            reply="모든 항목이 이미 채워졌습니다!",
            updated_field=None,
            is_finished=True,
            full_contract_data=content
        )

    # 실제 필드 처리
    ai = await get_smart_extraction(
        client,
        current_item["field_id"],
        message,
        current_item["question"]
    )

    # ✅ AI가 반환한 filled_fields 적용
    new_fields = ai.get("filled_fields", {})
    content.update(new_fields)

    # ✅ skip_next_n_questions 적용
    skip_n = ai.get("skip_next_n_questions", 0)
    for _ in range(skip_n):
        _, idx = find_next_question(content)
        if idx < len(CONTRACT_SCENARIO):
            content[CONTRACT_SCENARIO[idx]["field_id"]] = "__SKIPPED__"

    # ✅ follow-up 질문이 있으면 그대로 반환
    if ai.get("status") == "clarify":
        return schemas.ChatResponse(
            reply=ai["follow_up_question"],
            updated_field=None,
            is_finished=False,
            full_contract_data=content
        )

    # ✅ 다음 질문 찾기
    next_item, _ = find_next_question(content)

    if next_item:
        updated_key = list(new_fields.keys())[0]
        return schemas.ChatResponse(
            reply=next_item["question"],
            updated_field=schemas.UpdatedField(
            field_id=updated_key,
            value=new_fields[updated_key]
    ),
    is_finished=False,
    full_contract_data=content
)

    else:
        return schemas.ChatResponse(
            reply="모든 항목이 작성되었습니다.",
            updated_field=schemas.UpdatedField(
                field_id=updated_key,
                value=new_fields[updated_key]
            ),
            is_finished=True,
            full_contract_data=content
)



# -----------------------------------------------------------
# ✅ 5. DOCX 렌더링
# -----------------------------------------------------------
TEMPLATE_FILE = "working.docx"

async def render_docx(contract):
    """근로계약서 템플릿(.docx)을 렌더링해 DocxTemplate 객체로 반환."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(current_dir, "..", "templates", TEMPLATE_FILE)

    doc = DocxTemplate(template_path)
    doc.render(contract.content or {})
    return doc