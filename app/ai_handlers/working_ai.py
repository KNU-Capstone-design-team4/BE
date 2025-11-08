import datetime
from typing import List, Dict, Optional, Any, Tuple
from openai import AsyncOpenAI
import os
import json

# --- 1. 근로계약서 전용 시나리오 ---
CONTRACT_SCENARIO_LABOR = [
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
    scenario = CONTRACT_SCENARIO_LABOR
    
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