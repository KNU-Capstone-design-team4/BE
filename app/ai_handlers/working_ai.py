import datetime
from typing import List, Dict, Optional, Any, Tuple
from openai import AsyncOpenAI
import os
import json
import numpy as np  
from docxtpl import DocxTemplate, RichText
from ..import models, schemas, crud
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession

client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

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

SIMILARITY_THRESHOLD = 0.4
tip_embeddings: List[np.ndarray] = []
tip_embeddings_lock = asyncio.Lock()


# --- 2. (⭐️ 신규) 근로계약서 전용 RAG 함수 ---
async def get_tip_embeddings():
    """근로계약서 팁 목록 임베딩을 (최초 1회) 생성하고 캐시합니다."""
    global tip_embeddings
    async with tip_embeddings_lock:
        if not tip_embeddings:
            print("RAG 팁 목록 임베딩을 생성합니다... (근로계약서)")
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
    top_score = sims[idx[0]] if idx.size > 0 else 0.0
    tips_str = "\n".join([TIP_LIST[i] for i in idx])
    return tips_str, top_score

async def get_rag_response(question: str, relevant_tips: str) -> str:
    """(⭐️ 신규) 근로계약서(노무사) 전용 RAG 프롬프트"""
    system_prompt = f"""
    당신은 주어진 '참고 자료'만을 기반으로 답변하는 AI 노무사입니다. 다음 규칙을 엄격히 따르세요.

    --- 참고 자료 ---
    {relevant_tips}
    -----------------

    [규칙]
    1.  [생각 단계]: 먼저 사용자의 질문을 분석하고, '참고 자료'에서 관련된 모든 조항을 찾습니다.
    2.  [답변 생성 단계]: '생각 단계'의 논리를 바탕으로, 사용자에게 최종적인 답변을 친절하고 명확하게 생성합니다.
    3.  [출처 명시 단계]: 답변 내용의 근거가 된 '참고 자료'의 '팁 번호'를 문장 끝에 (출처: 팁 N번) 형식으로 반드시 포함합니다.
    """
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        temperature=0
    )
    return resp.choices[0].message.content.strip()

# --- 1. (⭐️ 3. 수정) HTML + DOCX 모두를 위한 시나리오 ---
CONTRACT_SCENARIO_LABOR = [
    # 1. 당사자 정보
    {"field_id": "employer", "question": "먼저, 계약을 체결하는 '사업주'의 명칭(또는 성함)은 무엇인가요? (예: (주)한빛유통)"},
    {"field_id": "employee", "question": "이제 '근로자'의 성함은 무엇인가요? (예: 김철수)"},

    # 2. 계약 기간 및 장소
    {"field_id": "start_date_year", "question": "실제 근로를 시작하는 날(근로개시일)의 '년도'를 숫자로 알려주세요. (예: 2025)"},
    {"field_id": "start_date_month", "question": "근로개시일의 '월'을 숫자로 알려주세요. (예: 11)"},
    {"field_id": "workplace", "question": "근무하게 될 실제 장소(근무장소)를 알려주세요. (예: 사업장과 동일)"},
    {"field_id": "job_description", "question": "근로자가 수행할 업무 내용(직종)은 무엇인가요? (예: 사무 보조 및 서류 정리)"},

    # 3. 근로시간 및 휴일
    {"field_id": "start_time", "question": "하루 근로를 시작하는 시간(시업 시간)을 알려주세요. (예: 09:00)"},
    {"field_id": "end_time", "question": "하루 근로를 마치는 시간(종업 시간)을 알려주세요. (예: 18:00)"},
    {"field_id": "break_time", "question": "휴게 시간은 몇 시부터 몇 시까지인가요? (예: 12:00 - 13:00)"},
    {"field_id": "work_day", "question": "일주일에 '총 몇 일'을 근무하나요? (숫자만 입력, 예: 5)"},
    {"field_id": "off_day", "question": "주휴일(유급휴일)로 지정된 요일은 무엇인가요? (예: 매주 일요일)"},

    # 4. 임금 (급여)
    {"field_id": "wage", "question": "월(일, 시간)급 총 임금액을 숫자로만 알려주세요. (예: 2500000)"},
    {"field_id": "bonus", "question": "별도로 정기적인 상여금이 지급되나요? (예: 100만원 / 없음)"},
    
    # (⭐️ 4. 수정) HTML에 맞춰 'allowance' (있음/없음) 질문 추가
    {"field_id": "allowance", "question": "상여금 외 기타 급여(제수당 등)가 지급되나요? (예: 있음/없음)"},
    
    # (HTML의 4개 입력칸)
    {"field_id": "other_allowance_1", "question": "기타 급여 첫 번째 항목과 금액을 알려주세요. (없으면 '없음' 입력)"},
    {"field_id": "other_allowance_2", "question": "기타 급여 두 번째 항목과 금액을 알려주세요. (없으면 '없음' 입력)"},
    {"field_id": "other_allowance_3", "question": "기타 급여 세 번째 항목과 금액을 알려주세요. (없으면 '없음' 입력)"},
    {"field_id": "other_allowance_4", "question": "기타 급여 네 번째 항목과 금액을 알려주세요. (없으면 '없음' 입력)"},
    
    {"field_id": "payday", "question": "임금은 매월 며칠에 지급되나요? (숫자만 입력, 예: 25)"},
    {"field_id": "payment_method", "question": "임금 지급 방법은 '계좌이체'인가요, '직접 현금 지급'인가요?"},
    
    # 5. 사회보험
    {"field_id": "employment_insurance", "question": "고용보험에 가입하나요? (예: 예/아니오)"},
    {"field_id": "industrial_accident_insurance", "question": "산재보험에 가입하나요? (예: 예/아니오)"},
    {"field_id": "national_pension", "question": "국민연금에 가입하나요? (예: 예/아니오)"},
    {"field_id": "health_insurance", "question": "건강보험에 가입하나요? (예: 예/아니오)"},

    # 11. 계약일
    {"field_id": "contract_year", "question": "이 근로계약서를 최종적으로 작성한 날짜의 '년도'는 언제인가요? (예: 2025)"},
    {"field_id": "contract_month", "question": "계약서 작성일의 '월'은 언제인가요? (예: 10)"},
    {"field_id": "contract_day", "question": "계약서 작성일의 '일'은 언제인가요? (예: 20)"},

    # HTML 하단 서명란
    {"field_id": "employer_name", "question": "사업주 서명란의 '사업체명'을 다시 한번 입력해주세요. (예: (주)한빛유통)"},
    {"field_id": "employer_phone", "question": "사업주 서명란의 '전화번호'를 입력해주세요."},
    {"field_id": "employer_address", "question": "사업주 서명란의 '주소'를 입력해주세요."},
    {"field_id": "employer_representative", "question": "사업주 서명란의 '대표자 성명'을 입력해주세요. (예: 김철수)"},
    {"field_id": "employee_address", "question": "근로자 서명란의 '주소'를 입력해주세요."},
    {"field_id": "employee_phone", "question": "근로자 서명란의 '연락처'를 입력해주세요."},
    {"field_id": "employee_name", "question": "근로자 서명란의 '성명'을 입력해주세요. (예: 김철수)"},
]


async def get_smart_extraction(
    field_id: str, 
    user_message: str, 
    question: str
) -> Dict:
    
    today = datetime.date.today()
    current_year = today.year
    
    # ❗️ (F-string 버그 수정 1) JSON 예시를 별도 변수로 분리
    json_format_example = '{"status": "...", "filled_fields": {"key": "value", ...}, "skip_next_n_questions": 0, "follow_up_question": null}'
    
    # ❗️ (F-string 버그 수정 2) f-string에서 {json_format_example} 변수 사용
    base_system_prompt = f"""
    당신은 사용자의 답변에서 핵심 정보를 추출하는 '스마트 폼 어시스턴트'입니다.
    오늘은 {today.strftime('%Y년 %m월 %d일')}입니다. (현재 연도는 {current_year}년)

    [규칙]
    1.  사용자의 답변(`user_message`)이 현재 질문(`question`)에 대해 충분하면, `status: "success"`를 반환합니다.
    2.  답변이 모호하거나 정보가 부족하면 `status: "clarify"`와 `follow_up_question`을 생성합니다.
    3.  `filled_fields`에는 템플릿(HTML, DOCX)에 필요한 모든 키와 값을 채워야 합니다.
        - HTML 체크박스: `true` / `false` 값을 사용합니다.
        - DOCX 괄호: "O" / " " (공백) 값을 사용합니다.
        - DOCX 체크박스: "☑" (U+2612) / "☐" (U+2610) 값을 사용합니다.
    4.  `skip_next_n_questions`는 '없음'을 선택하여 다음 질문이 불필요할 때 사용됩니다.
    5.  반드시 지정된 JSON 형식으로만 반환해야 합니다.

    [JSON 반환 형식]
    {json_format_example}
    """
    
    specific_examples = ""
    
    # [날짜 - 년도]
    if field_id.endswith("_year"):
        specific_examples = f"""
        [예시 1: 날짜 (연도)]
        question: "{question}"
        user_message: "2025년이요"
        AI: {{"status": "success", "filled_fields": {{"{field_id}": "2025"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """

    # [휴게시간] (두 값을 하나로)
    elif field_id == "break_time":
        specific_examples = f"""
        [예시 1: 휴게시간]
        question: "휴게 시간은 몇 시부터 몇 시까지인가요? (예: 12:00 - 13:00)"
        user_message: "12시부터 1시까지요"
        AI: {{"status": "success", "filled_fields": {{"break_time_start": "12:00", "break_time_end": "13:00"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """
    
    # [상여금] (HTML + DOCX 동시 지원)
    elif field_id == "bonus":
        specific_examples = """
        [예시 1: '있음' 선택 (금액 입력)]
        question: "별도로 정기적인 상여금이 지급되나요? (예: 100만원 / 없음)"
        user_message: "네 100만원이요"
        AI: {{"status": "success", "filled_fields": {
            "bonus_amount": "100만원", 
            "bonus_none": false,
            "is_bonus_paid_yes_o": "O",
            "is_bonus_paid_no_o": " "
        }, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 2: '없음' 선택]
        question: "별도로 정기적인 상여금이 지급되나요? (예: 100만원 / 없음)"
        user_message: "아니요 없습니다"
        AI: {{"status": "success", "filled_fields": {
            "bonus_amount": "", 
            "bonus_none": true,
            "is_bonus_paid_yes_o": " ",
            "is_bonus_paid_no_o": "O"
        }, "skip_next_n_questions": 0, "follow_up_question": null}}
        
        [예시 3: '있음'만 선택 (되묻기)]
        question: "별도로 정기적인 상여금이 지급되나요? (예: 100만원 / 없음)"
        user_message: "네"
        AI: {{"status": "clarify", "filled_fields": {
            "bonus_none": false,
            "is_bonus_paid_yes_o": "O",
            "is_bonus_paid_no_o": " "
        }, "skip_next_n_questions": 0, "follow_up_question": "알겠습니다. 상여금은 얼마인가요?"}}
        """

    # [기타급여 - 있음/없음] (⭐️ V5 수정)
    elif field_id == "allowance":
        specific_examples = """
        [예시 1: '있음' 선택 (다음 질문으로 이동)]
        question: "상여금 외 기타 급여(제수당 등)가 지급되나요? (예: 있음/없음)"
        user_message: "네 있습니다"
        AI: {{"status": "success", "filled_fields": {
            "other_allowance": null, /* HTML의 <input type="text">는 비워둠 */
            "other_allowance_none": false,
            "is_allowance_paid_yes_o": "O",
            "is_allowance_paid_no_o": " "
        }, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 2: '없음' 선택 (다음 4개 질문 스킵)]
        question: "상여금 외 기타 급여(제수당 등)가 지급되나요? (예: 있음/없음)"
        user_message: "아니요 없어요"
        AI: {{"status": "success", "filled_fields": {
            "other_allowance": "",
            "other_allowance_none": true,
            "is_allowance_paid_yes_o": " ",
            "is_allowance_paid_no_o": "O",
            "other_allowance_1": "", 
            "other_allowance_2": "", 
            "other_allowance_3": "", 
            "other_allowance_4": ""
        }, "skip_next_n_questions": 4, "follow_up_question": null}}
        """

    # [기타급여 - 4개 항목]
    elif field_id.startswith("other_allowance_"):
        specific_examples = f"""
        [예시 1: '있음' 선택 (금액 입력)]
        question: "{question}"
        user_message: "네 식대 10만원이요"
        AI: {{"status": "success", "filled_fields": {{"{field_id}": "식대 10만원"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        
        [예시 2: '없음' 선택 (공백 저장)]
        question: "{question}"
        user_message: "아니요 없어요"
        AI: {{"status": "success", "filled_fields": {{"{field_id}": ""}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """

    # [지급방법] (HTML + DOCX 동시 지원)
    elif field_id == "payment_method":
        specific_examples = """
        [예시 1: '계좌이체' 선택]
        question: "임금 지급 방법은 '계좌이체'인가요, '직접 현금 지급'인가요?"
        user_message: "통장으로 받을게요"
        AI: {{"status": "success", "filled_fields": {
            "direct_pay": false, 
            "bank_pay": true,
            "payment_method_direct_o": " ",
            "payment_method_bank_o": "O"
        }, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 2: '직접 지급' 선택]
        question: "임금 지급 방법은 '계좌이체'인가요, '직접 현금 지급'인가요?"
        user_message: "현금으로 직접 받고 싶어요"
        AI: {{"status": "success", "filled_fields": {
            "direct_pay": true, 
            "bank_pay": false,
            "payment_method_direct_o": "O",
            "payment_method_bank_o": " "
        }, "skip_next_n_questions": 0, "follow_up_question": null}}
        """
    
    # [사회보험] (HTML + DOCX 동시 지원)
    elif field_id in ["employment_insurance", "industrial_accident_insurance", "national_pension", "health_insurance"]:
        # DOCX용 변수명 (예: apply_employment_insurance_check)
        check_variable_name = f"apply_{field_id}_check" 
        
        specific_examples = f"""
        [예시 1: '예' 선택 (HTML: true, DOCX: ☒)]
        question: "{question}"
        user_message: "네 가입해요"
        AI: {{"status": "success", "filled_fields": {
            "{field_id}": true,
            "{check_variable_name}": "☑"
        }, "skip_next_n_questions": 0, "follow_up_question": null}}
        
        [예시 2: '아니오' 선택 (HTML: false, DOCX: ☐)]
        question: "{question}"
        user_message: "아니요"
        AI: {{"status": "success", "filled_fields": {
            "{field_id}": false,
            "{check_variable_name}": "☐"
        }, "skip_next_n_questions": 0, "follow_up_question": null}}
        """
    
    # [기본] 예시 (단순 텍스트)
    else: 
        specific_examples = f"""
        [예시 1: 일반 텍스트 추출]
        question: "{question}"
        user_message: "저희 회사는 (주)한빛유통입니다."
        AI: {{"status": "success", "filled_fields": {{"{field_id}": "(주)한빛유통"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        
        [예시 2: 전화번호 추출]
        question: "{question}"
        user_message: "제 번호는 010-1234-5678입니다"
        AI: {{"status": "success", "filled_fields": {{"{field_id}": "010-1234-5678"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """

    system_prompt_with_examples = f"{base_system_prompt}\n--- [필드별 퓨샷(Few-Shot) 예시] ---\n{specific_examples}"
    
    try:
        # (⭐️ 수정) 이 파일의 'client'를 사용
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": f"{base_system_prompt}\n--- [필드별 퓨샷(Few-Shot) 예시] ---\n{specific_examples}"},
                {"role": "user", "content": f"question: \"{question}\"\nuser_message: \"{user_message}\""},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        
        ai_response_str = response.choices[0].message.content
        ai_response_json = json.loads(ai_response_str)
        return ai_response_json
    except Exception as e:
        print(f"OpenAI (get_smart_extraction - labor_contract) API call failed: {e}")
        return {
            "status": "success", 
            "filled_fields": {field_id: user_message}, 
            "skip_next_n_questions": 0,
            "follow_up_question": None
        }
    
def find_next_question(
    current_content: Dict[str, Any]
) -> Tuple[Optional[Dict], int]:
    """
    현재 content를 기반으로 다음에 물어볼 질문(item)과 인덱스(index)를 반환합니다.
    (HTML 'name' 속성 기준 V5 로직)
    """
    scenario = CONTRACT_SCENARIO_LABOR
    
    current_question_item: Optional[Dict] = None
    current_question_index = -1 

    for i, item in enumerate(scenario):
        field_id = item["field_id"]
        
        # [기본 체크]
        if field_id in current_content:
            continue
            
        # [특수 로직 체크]
        # 'bonus' 질문 차례인데, 'bonus_amount'나 'bonus_none'이 이미 채워져있으면 건너뛰기
        if field_id == "bonus" and ("bonus_amount" in current_content or "bonus_none" in current_content):
            continue
        
        # 'allowance' (있음/없음) 질문을 체크
        if field_id == "allowance" and ("other_allowance_none" in current_content or "is_allowance_paid_yes_o" in current_content):
            continue
            
        # 'other_allowance_1' 질문 차례인데 'other_allowance_none'이 'true'이면 스킵
        if field_id.startswith("other_allowance_") and current_content.get("other_allowance_none") == True:
             continue
            
        if field_id == "payment_method" and ("direct_pay" in current_content or "bank_pay" in current_content):
            continue
        
        if field_id == "break_time" and "break_time_start" in current_content:
            continue
            
        # 다음 질문 찾음
        current_question_index = i
        current_question_item = item
        break
    
    if current_question_item is None:
        current_question_index = len(scenario)

    return current_question_item, current_question_index
# --- ⬆️ 여기까지 ⬆️ ---



async def process_message(
    # (⭐️ 수정) 이 함수는 DB 저장을 위해 db와 contract가 필요합니다.
    db: AsyncSession,
    contract: models.Contract,
    message: str
) -> schemas.ChatResponse:

    content = contract.content or {}
    
    # (참고: chat_history는 schemas.ChatResponse에 없으므로 임시 제거)
    # new_chat_history = contract.chat_history.copy() if ...

    # ✅ 1) 다음 질문 찾기
    current_item, current_index = find_next_question(content)
    current_bot_question = current_item["question"] if current_item else None

    # ✅ 2) 아무 입력 없으면 "시작/재개"
    if not message.strip() or message.strip() == "string":
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

    # ✅ 3) RAG 여부 판단 (이 파일의 RAG 함수 사용)
    tips, score = await find_top_relevant_tips(message)
    is_legal_question = score >= SIMILARITY_THRESHOLD

    if is_legal_question:
        rag = await get_rag_response(message, tips)
        follow = (
            f"\n\n[이어서 진행]\n{current_item['question']}"
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
    
    # (⭐️ 수정) 'client' 인자 전달 제거
    ai = await get_smart_extraction(
        current_item["field_id"],
        message,
        current_item["question"]
    )

    new_fields = ai.get("filled_fields", {})
    
    # (⭐️ 수정) AI가 반환한 filled_fields를 content에 즉시 반영 (DB 저장을 위해)
    content.update(new_fields)

    skip_n = ai.get("skip_next_n_questions", 0)
    for _ in range(skip_n):
        # (⭐️ 수정) 'content'가 업데이트되었으므로 find_next_question을 다시 호출
        _, idx = find_next_question(content)
        if idx < len(CONTRACT_SCENARIO_LABOR):
             # (⭐️ 수정) DB 저장을 위해 스킵된 필드도 content에 반영
            content[CONTRACT_SCENARIO_LABOR[idx]["field_id"]] = "__SKIPPED__"

    # --- ⬇️ (⭐️ 5. 핵심 수정) DB 저장 로직 추가 ⬇️ ---
    # (foreign_ai.py에는 이 부분이 누락되어 있었습니다)
    try:
        # crud.py의 함수를 호출하여 DB에 최종 content를 저장
        await crud.update_contract_content_multiple(db, contract, content)
    except Exception as e:
        print(f"DB 업데이트 실패: {e}")
        # (DB 저장 실패 시, 사용자에게 에러 반환)
        return schemas.ChatResponse(
            reply=f"데이터 저장 중 오류가 발생했습니다: {e}",
            updated_field=None,
            is_finished=False,
            full_contract_data=contract.content or {} # 롤백된 원본 데이터
        )
    # --- ⬆️ DB 저장 로직 끝 ⬆️ ---

    # ✅ 6) follow-up 질문이 있으면 그대로 반환 (DB 저장은 위에서 했음)
    if ai.get("status") == "clarify":
        return schemas.ChatResponse(
            reply=ai["follow_up_question"],
            updated_field=None, # DB는 업데이트되었지만, FR엔 새 필드 정보 안 줌
            is_finished=False,
            full_contract_data=content
        )

    # ✅ 7) 다음 질문 찾기
    next_item, _ = find_next_question(content)

    # (⭐️ 수정) schemas.UpdatedField 형식에 맞게 변환
    updated_field_list = [
        schemas.UpdatedField(field_id=k, value=v) for k, v in new_fields.items()
    ] if new_fields else None
    
    if next_item:
        return schemas.ChatResponse(
            reply=next_item["question"],
            updated_field=updated_field_list,
            is_finished=False,
            full_contract_data=content
        )
    else:
        return schemas.ChatResponse(
            reply="모든 항목이 작성되었습니다.",
            updated_field=updated_field_list,
            is_finished=True,
            full_contract_data=content
        )
# --- 4. DOCX 렌더링 함수 ---
# (이 함수는 HTML name 속성이 아닌, DOCX {{...}} 변수명 기준으로 작동해야 함)
TEMPLATE_FILE = "working.docx" 

async def render_docx(contract: models.Contract) -> DocxTemplate:
    """
    DB에 저장된 계약서 정보로 .docx (워드) 문서를 생성합니다.
    (RichText를 적용하여 폰트 깨짐을 방지합니다.)
    """
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(current_dir, "..", "..", "templates", TEMPLATE_FILE)
    
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"템플릿 파일을 찾을 수 없습니다: {template_path}")

    doc = DocxTemplate(template_path, autoescape=True) 
    
    raw_context = contract.content or {} 
    context = {}
    
    # (⭐️ 7. 수정) 폰트가 깨지는 필드 목록 (DOCX {{...}} 변수명 기준)
    richtext_fields = [
        "employer_name", "employee_name", "start_date_full", "work_location", 
        "job_description", "start_time", "end_time", "rest_time", "work_day", 
        "Weekly_Paid_Holiday", "salary_amount", "bonus_amount", 
        "allowance_details", # (⭐️ V5 수정) DOCX는 4개 항목을 하나의 필드로 쓸 수 있음
        "other_allowance_1", "other_allowance_2", "other_allowance_3", "other_allowance_4",
        "salary_payment_date", "contract_date_full", "business_name", 
        "business_phone", "business_address", "employee_address", "employee_phone"
    ]
    
    for key, value in raw_context.items():
        if key in richtext_fields:
            rt = RichText()
            rt.add(str(value if value else "")) 
            context[key] = rt
        else:
            # true/false, O/X, ☑/☐ 등은 그대로 사용
            context[key] = value
            
    # (⭐️ 8. 신규) 4개의 기타급여를 'allowance_details' 하나로 합치기
    # (DOCX 템플릿이 "기타급여(제수당 등) : {{ allowance_details }} 원" 형태일 경우)
    details_list = [
        raw_context.get("other_allowance_1", ""),
        raw_context.get("other_allowance_2", ""),
        raw_context.get("other_allowance_3", ""),
        raw_context.get("other_allowance_4", "")
    ]
    # 빈 문자열이 아닌 항목들만 쉼표(,)로 연결
    final_details = ", ".join(filter(None, details_list))
    
    # 폰트 깨짐 방지를 위해 RichText로 다시 변환
    rt_details = RichText()
    rt_details.add(final_details)
    context["allowance_details"] = rt_details # 템플릿 변수명

    doc.render(context)
    return doc