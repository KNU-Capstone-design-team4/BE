import os
import json
import uuid
import datetime
import numpy as np
import asyncio
from pathlib import Path
from typing import Dict, Optional, Any, Tuple, List
from openai import AsyncOpenAI
from docxtpl import DocxTemplate
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas

client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# -----------------------------------------------------------
# 1. 임대차 계약서 전용 시나리오 (질문 리스트)
# -----------------------------------------------------------
# ❗️ [TODO] 임대차 계약서 양식에 맞는 질문들로 채워주세요.
CONTRACT_SCENARIO = [
    # --- 1. 계약 종류 (분기점) ---
    {"field_id": "contract_type", "question": "계약의 종류를 선택해주세요. (전세 / 월세)"},

    # --- 2. 부동산의 표시 (기본 정보) ---
    {"field_id": "location", "question": "임대할 부동산의 소재지(주소)를 입력해주세요."},
    {"field_id": "land", "question": "토지의 지목을 알려주세요. (예: 대, 전, 답 등)"},
    {"field_id": "land_area", "question": "토지의 면적(㎡)을 알려주세요."},
    {"field_id": "building", "question": "건물의 구조 및 용도를 알려주세요. (예: 철근콘크리트조, 주택)"},
    {"field_id": "build_area", "question": "건물의 면적(㎡)을 알려주세요."},
    {"field_id": "lease_por", "question": "임대할 부분은 어디인가요? (예: 2층 201호 전체)"},
    {"field_id": "les_area", "question": "임대할 부분의 면적(㎡)은 얼마인가요?"},

    # --- 3. 계약 내용 (보증금 및 지급 시기) ---
    {"field_id": "deposit", "question": "보증금 총액은 얼마인가요?"}, # -> {{deposit}}
    {"field_id": "con_dep", "question": "계약금(계약 시 지불하는 금액)은 얼마인가요? 그리고 영수자(집주인)의 이름도 알려주세요"}, # -> {{con_dep}}
    
    {"field_id": "middle_payment_info", "question": "중도금이 있다면 금액과 지불 날짜를 알려주세요. (없으면 '없음'이라고 답해주세요)"}, 
    # -> AI가 {{med_dep}}, {{m_y}}, {{m_m}}, {{m_d}} 로 분리

    {"field_id": "balance_payment_info", "question": "잔금 금액과 지불 날짜를 알려주세요."}, 
    # -> AI가 {{re_dep}}, {{re_y}}, {{re_m}}, {{re_d}} 로 분리

    # --- 4. 차임 (월세일 경우에만 질문 - 조건부) ---
    {"field_id": "monthly_rent_info", "question": "월세(차임) 금액과 매월 지불하는 날짜(예: 매월 5일)을 알려주고 선불인지 후불인지 알려주세요."},
    # -> AI가 {{c_wag}}, {{c_d}} 로 분리

    # --- 5. 계약 기간 ---
    {"field_id": "lease_term", "question": "임대차 기간(시작일 ~ 종료일)을 알려주세요."},
    # -> AI가 {{s_y}}, {{s_m}}, {{s_d}} (시작) / {{e_y}}, {{e_m}}, {{e_d}} (종료) 로 분리

    # --- 6. 인적 사항 (임대인) ---
    {"field_id": "leor_name", "question": "임대인(집주인)의 성함을 알려주세요."},
    {"field_id": "lessor_aut", "question": "임대인의 주민등록번호를 알려주세요."},
    {"field_id": "leor_num", "question": "임대인의 전화번호를 알려주세요."},
    {"field_id": "lessor_add", "question": "임대인의 주소를 알려주세요."},
    {"field_id": "lessor_agn", "question": "임대인의 대리인이 있나요?"},    
    {"field_id": "les_agn_add", "question": "대리인의 주소를 알려주세요."},
    {"field_id": "les_agn_num", "question": "대리인의 주민등록번호를 알려주세요."},
    {"field_id": "les_agn_name", "question": "대리인의 성명을 알려주세요."},


    # --- 7. 인적 사항 (임차인) ---
    {"field_id": "less_name", "question": "임차인(세입자)의 성함을 알려주세요."},
    {"field_id": "less_aut", "question": "임차인의 주민등록번호를 알려주세요."},
    {"field_id": "less_num", "question": "임차인의 전화번호를 알려주세요."},
    {"field_id": "lessee_add", "question": "임차인의 주소를 알려주세요."},
    {"field_id": "less_agn", "question": "임차인의 대리인이 있나요?"},
    {"field_id": "less_agn_add", "question": "대리인의 주소를 알려주세요."},
    {"field_id": "less_agn_num", "question": "대리인의 주민등록번호를 알려주세요."},
    {"field_id": "less_agn_name", "question": "대리인의 성명을 알려주세요."},
    
    # --- 8. 특약 사항 ---
    {"field_id": "special_terms", "question": "추가할 특약사항이 있다면 말씀해주세요. (없으면 '없음'이라고 답해주세요)"} 
    # -> 템플릿에 {{special_terms}} 변수가 있다고 가정 (소스 31)
]

# -----------------------------------------------------------
# 2. 임대차 계약서 전용 법률 팁 (RAG 지식 베이스)
# -----------------------------------------------------------
# ❗️ [TODO] 주택임대차보호법 등 관련 법령 정보를 채워주세요.
TIP_LIST = [
    "대리인을 포함한 계약이라면 특약사항에 대리계약임을 명시하는 것이 좋다.",
    ""
    # (예시)
    # "1. (대항력) 임차인이 주택의 인도와 주민등록을 마친 때에는 그 다음 날부터 제3자에 대하여 효력이 생긴다.",
    # "2. (우선변제권) 대항요건과 확정일자를 갖춘 임차인은 경매 시 후순위 권리자보다 우선하여 보증금을 변제받을 권리가 있다.",
    # ...
]

# RAG 임계값 (필요시 조정)
SIMILARITY_THRESHOLD = 0.6

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
    # 팁 리스트가 비어있으면 빈 결과 반환 (오류 방지)
    if not TIP_LIST:
        return "", 0.0
        
    embeddings = await get_tip_embeddings()
    q_emb = await get_embedding(question)
    sims = [np.dot(q_emb, t) for t in embeddings]

    idx = np.argsort(sims)[-top_n:][::-1]
    top_score = sims[idx[0]]
    tips_str = "\n".join([TIP_LIST[i] for i in idx])
    return tips_str, top_score

async def get_rag_response(question: str, relevant_tips: str) -> str:
    system_prompt = f"""
    당신은 '부동산 임대차 계약 전문 AI 법률 상담관'입니다.
    
    당신의 답변은 반드시 아래의 '참고 자료(팁 목록)'에 기반하여야 합니다.
    (TIP_LIST에 없는 내용은 단정짓지 말고 "참고 자료의 범위 내에서..."라고 제한적으로 표현하세요.)

    --- 참고 자료(임대차 계약 관련 TIP) ---
    {relevant_tips}
    -----------------------------------------

    [답변 규칙]
    1. 당신의 역할은 임대차 계약서 작성 및 주택임대차보호법 관련 상담입니다.
    2. 답변은 핵심 쟁점 정리 -> 참고 자료에 근거한 답변 -> 추가 안내 순서로 작성하세요.
    3. 마지막 줄에 '출처: 팁 N번' 형식으로 근거를 명시하세요.
    4. 불필요한 인사말은 생략하고 답변만 하세요.
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

# -----------------------------------------------------------
# 3. 임대차 계약서 전용 AI 추출기
# -----------------------------------------------------------
async def get_smart_extraction(
    client: AsyncOpenAI,
    field_id: str, 
    user_message: str, 
    question: str
) -> Dict:
    
    today = datetime.date.today()
    current_year = today.year
    json_format_example = '{"status": "...", "filled_fields": {"key": "value", ...}, "skip_next_n_questions": 0, "follow_up_question": null}'
    
    base_system_prompt = f"""
    당신은 '부동산 임대차 계약서' 작성을 돕는 전문 AI 어시스턴트입니다.
    사용자의 답변에서 계약서 서식에 필요한 핵심 정보를 추출하여 JSON으로 반환하세요.
    오늘은 {today.strftime('%Y년 %m월 %d일')}입니다.

    [규칙]
    1. `filled_fields`의 key는 템플릿 변수명과 일치해야 합니다.
    2. [날짜]는 년(y), 월(m), 일(d) 변수로 분리하여 저장해야 합니다. (예: 2024-10-25 -> _y:2024, _m:10, _d:25)
    3. [체크박스] 전세/월세는 변수에 true 또는 false로 채워야 합니다.
    4. [스킵] 스킵하는 필드(예: 전세일 때 월세 관련 필드)는 빈 문자열 ""을 채워야 합니다.
    5. 사용자가 법률적 질문을 하면 `status`를 "rag_required"로 반환하세요.
    
    [JSON 반환 형식]
    {json_format_example}
    """
    
    specific_examples = ""
    
    # [분기 1: 계약 종류] (전세 vs 월세)
    if field_id == "contract_type":
        # 전세 선택 시: 월세 관련 질문(monthly_rent_info) 1개 스킵 + 변수 비우기
        jeonse_skip_fields = {"c_wag": "", "c_d": "", "payment": ""} 
        
        # 월세 선택 시: 스킵 없음
        monthly_skip_fields = {} # 월세는 다 물어봐야 함

        specific_examples = f"""
        [예시 1: 전세 선택 (월세 질문 스킵)]
        question: "{question}"
        user_message: "전세 계약입니다."
        AI: {{"status": "success", "filled_fields": {{"charter": true, "mntly": false, "c_wag": "", "c_d": ""}}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 2: 월세 선택 (스킵 없음)]
        question: "{question}"
        user_message: "월세로 하려고요."
        AI: {{"status": "success", "filled_fields": {{"charter": false, "mntly": true}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """
    
    # -----------------------------------------------------------
    #   임대인 대리인 분기
    # -----------------------------------------------------------
    elif field_id == "lessor_agn":
        # 대리인 없음 -> 관련 필드 3개 스킵 처리
        no_agent_fields = {
            "lessor_agn": "없음", # 제어용 값
            "les_agn_add": "",
            "les_agn_num": "",
            "les_agn_name": ""
        }
        # 대리인 있음 -> 단순히 "있음"만 기록하고 다음 질문으로 진행
        yes_agent_fields = {"lessor_agn": "있음"}

        specific_examples = f"""
        [예시 1: 대리인 없음]
        question: "{question}"
        user_message: "아니요, 집주인이 직접 옵니다."
        AI: {{"status": "success", "filled_fields": {json.dumps(no_agent_fields)}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 2: 대리인 있음 (다음 질문 진행)]
        question: "{question}"
        user_message: "네, 아드님이 대리인으로 오세요."
        AI: {{"status": "success", "filled_fields": {json.dumps(yes_agent_fields)}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """

    # -----------------------------------------------------------
    #   임차인 대리인 분기
    # -----------------------------------------------------------
    elif field_id == "less_agn":
        # 대리인 없음 -> 관련 필드 3개 스킵 처리
        no_agent_fields = {
            "less_agn": "없음", # 제어용 값
            "less_agn_add": "",
            "less_agn_num": "",
            "less_agn_name": ""
        }
        # 대리인 있음
        yes_agent_fields = {"less_agn": "있음"}

        specific_examples = f"""
        [예시 1: 대리인 없음]
        question: "{question}"
        user_message: "없습니다."
        AI: {{"status": "success", "filled_fields": {json.dumps(no_agent_fields)}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 2: 대리인 있음 (다음 질문 진행)]
        question: "{question}"
        user_message: "네, 있습니다."
        AI: {{"status": "success", "filled_fields": {json.dumps(yes_agent_fields)}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """
    
    # [보증금]
    elif field_id == "deposit":
        specific_examples = f"""
        user_message: "백만원 입니다."
        AI: {{"status": "success", "filled_fields": {{"deposit": "100만원", "deposit_num": "1,000,000"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """
        
    # [계약금, 영수자]
    elif field_id == "con_dep":
        specific_examples = f"""
        user_message: "백만원을 홍길동에게 지급할 것 입니다."
        AI: {{"status": "success", "filled_fields": {{"con_dep": "100만원", "con_dep_recipient": "홍길동"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """
        
    # [복합 정보: 중도금] (금액 + 날짜 분리)
    elif field_id == "middle_payment_info":
        specific_examples = f"""
        [예시 1: 중도금 있음]
        user_message: "2천만원을 2024년 5월 1일에 줄게요."
        AI: {{"status": "success", "filled_fields": {{"med_dep": "20,000,000", "m_y": "2024", "m_m": "5", "m_d": "1"}}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 2: 중도금 없음]
        user_message: "중도금은 없습니다."
        AI: {{"status": "success", "filled_fields": {{"med_dep": "", "m_y": "", "m_m": "", "m_d": ""}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """

    # [복합 정보: 잔금] (금액 + 날짜 분리)
    elif field_id == "balance_payment_info":
        specific_examples = f"""
        [예시 1: 금액과 날짜를 모두 언급한 경우]
        question: "{question}"
        user_message: "나머지 1억은 입주하는 날인 2024년 6월 30일에 줍니다."
        AI: {{"status": "success", "filled_fields": {{"re_dep": "100,000,000", re_y": "2024", "re_m": "6", "re_d": "30"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        
        [예시 2: 금액만 언급한 경우 (날짜 재질문 유도)]
        question: "{question}"
        user_message: "1억 입니다."
        AI: {{"status": "clarify", "filled_fields": {{"re_dep": "100,000,000"}}, "skip_next_n_questions": 0, "follow_up_question": "잔금지급 날짜도 알려주세요."}}
        
        [예시 3: 날짜만 언급한 경우 (금액 재질문 유도)]
        question: "{question}"
        user_message: "2024.6.30일 입니다."
        AI: {{"status": "clarify", "filled_fields": {{"re_y": "2024", "re_m": "6", "re_d": "30"}}, "skip_next_n_questions": 0, "follow_up_question": "잔금 금액도 알려주세요."}}
        """

    # [복합 정보: 월세] (금액 + 날짜 분리)
    elif field_id == "monthly_rent_info":
        specific_examples = f"""
        [예시 1: 선불인 경우]
        question: "{question}"
        user_message: "월세 50만원이고 매달 25일에 선불로 냅니다."
        AI: {{"status": "success", "filled_fields": {{"c_wag": "500,000", "c_d": "25", "payment": "선불로"}}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 2: 후불인 경우]
        question: "{question}"
        user_message: "30만원, 10일, 후불입니다."
        AI: {{"status": "success", "filled_fields": {{"c_wag": "300,000", "c_d": "10", "payment": "후불로"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        
        [예시 3: 선불/후불 언급이 없는 경우 (재질문 유도)]
        question: "{question}"
        user_message: "50만원 25일이요."
        AI: {{"status": "clarify", "filled_fields": {{}}, "skip_next_n_questions": 0, "follow_up_question": "선불인가요, 후불인가요?"}}
        """
    # [복합 정보: 계약 기간] (시작일 + 종료일 분리)
    elif field_id == "lease_term":
        specific_examples = f"""
        user_message: "2024년 6월 1일부터 2026년 5월 31일까지입니다."
        AI: {{"status": "success", "filled_fields": {{"s_y": "2024", "s_m": "6", "s_d": "1", "e_y": "2026", "e_m": "5", "e_d": "31"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """

    # -----------------------------------------------------------
    # ❗️ [추가] 주민등록번호 입력 처리 (임대인, 임차인, 대리인 공통)
    # -----------------------------------------------------------
    elif field_id in ["lessor_aut", "less_aut", "les_agn_num", "less_agn_num"]:
        specific_examples = f"""
        [예시 1: 주민등록번호 추출]
        question: "{question}"
        user_message: "900101-1234567 입니다."
        AI: {{"status": "success", "filled_fields": {{"{field_id}": "900101-1234567"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        
        [예시 2: 숫자만 입력된 경우]
        question: "{question}"
        user_message: "9001011234567"
        AI: {{"status": "success", "filled_fields": {{"{field_id}": "900101-1234567"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """

    # -----------------------------------------------------------
    # ❗️ [추가] 전화번호 입력 처리 (임대인, 임차인 공통)
    # -----------------------------------------------------------
    elif field_id in ["leor_num", "less_num"]:
        specific_examples = f"""
        [예시 1: 전화번호 추출]
        question: "{question}"
        user_message: "010-1234-5678"
        AI: {{"status": "success", "filled_fields": {{"{field_id}": "010-1234-5678"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """

    else:
        # 기본 텍스트 추출 예시
        specific_examples = f"""
        question: "{question}"
        user_message: "홍길동입니다."
        AI: {{"status": "success", "filled_fields": {{"{field_id}": "홍길동"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """

    system_prompt_with_examples = f"{base_system_prompt}\n--- [필드별 퓨샷(Few-Shot) 예시] ---\n{specific_examples}"
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt_with_examples},
                {"role": "user", "content": f"question: \"{question}\"\nuser_message: \"{user_message}\""},
            ],
            temperature=0.0,
            response_format={"type": "json_object"}, 
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"OpenAI API Error: {e}")
        return {"status": "success", "filled_fields": {field_id: user_message}, "skip_next_n_questions": 0}

# -----------------------------------------------------------
# 4. 다음 질문 찾기 로직
# -----------------------------------------------------------
def find_next_question(current_content: Dict[str, Any]) -> Tuple[Optional[Dict], int]:
    scenario = CONTRACT_SCENARIO
    current_question_item: Optional[Dict] = None
    current_question_index = -1 

    for i, item in enumerate(scenario):
        field_id = item["field_id"]
        
        # 1. 기본적으로 값이 있으면 건너뜀
        if field_id in current_content:
            continue
            
        # 2. [특수 로직] 복합 필드 처리 (하나라도 채워지면 해당 질문 완료로 간주)
        if field_id == "contract_type" and ("charter" in current_content or "mntly" in current_content):
            continue
        if field_id == "middle_payment_info" and ("med_dep" in current_content or "m_y" in current_content):
            continue
        if field_id == "balance_payment_info" and ("re_dep" in current_content and "re_y" in current_content):
            continue
        if field_id == "monthly_rent_info" and ("c_wag" in current_content or "payment" in current_content):
            continue
        if field_id == "lease_term" and ("s_y" in current_content):
            continue
            
        # 3. [스킵 로직] '전세'인 경우 '월세' 질문 건너뛰기
        # AI가 전세를 선택하면 'c_wag'에 ""(빈 문자열)을 넣어줌 -> 위 2번 로직에 의해 건너뛰어짐
        # (따라서 별도 if문 불필요하지만, 명시적으로 확인 가능)

        current_question_index = i
        current_question_item = item
        break
    
    if current_question_item is None:
        current_question_index = len(scenario)

    return current_question_item, current_question_index

# -----------------------------------------------------------
# 5. 메시지 처리 (메인 로직)
# -----------------------------------------------------------
async def process_message(
    db: AsyncSession,
    contract,
    message: str
) -> schemas.ChatResponse:

    content = contract.content or {}
    
    # 계약 작성일(오늘) 자동 저장 (템플릿 변수 {{y}}, {{m}}, {{d}})
    if "y" not in content:
        today = datetime.date.today()
        content["y"] = str(today.year)
        content["m"] = str(today.month)
        content["d"] = str(today.day)
    
    new_chat_history = contract.chat_history.copy() if isinstance(contract.chat_history, list) else []

    # 1) 다음 질문 찾기
    current_item, current_index = find_next_question(content)
    
    current_bot_question = current_item["question"] if current_item else None    
    current_field_id = current_item["field_id"] if current_item else None

    # 2) 아무 입력 없으면 "시작/재개"
    if not message.strip():
        if current_item:
            return schemas.ChatResponse(
                reply=current_item["question"],
                updated_field=None,
                is_finished=False,
                full_contract_data=content,
                chat_history=new_chat_history
            )
        else:
            return schemas.ChatResponse(
                reply="모든 항목이 작성되었습니다! 추가로 궁금한 점이 있으신가요?",
                updated_field=None,
                is_finished=True,
                full_contract_data=content,
                chat_history=new_chat_history
            )
            
    # 공통 채팅 기록 저장
    if current_bot_question:
        new_chat_history.append({"sender": "bot", "message": current_bot_question})
    
    new_chat_history.append({"sender": "user", "message": message})
    
    # 3) AI 추출 및 의도 파악
    # (A) 폼 작성이 완료된 경우 -> 무조건 RAG 모드로 진입
    if current_item is None:
        ai_result = {"status": "rag_required"} 
    # (B) 폼 작성 중인 경우 -> AI에게 추출 시도
    else:
        ai_result = await get_smart_extraction(
            client,
            current_field_id,
            message,
            current_bot_question
        )

    # 4) RAG(법률 질문) 처리
    if ai_result.get("status") == "rag_required":
        tips, score = await find_top_relevant_tips(message)
        rag_answer = await get_rag_response(message, tips)
        
        new_chat_history.append({"sender": "bot", "message": rag_answer})

        # 후속 멘트
        if current_item:
            follow = f"\n\n(답변이 되셨나요? 이어서 진행합니다.)\n{current_item['question']}"
            is_finished = False
        else:
            follow = "\n\n(추가로 궁금한 점이 있으신가요? 언제든 물어봐 주세요.)"
            is_finished = True
            
        return schemas.ChatResponse(
            reply=rag_answer + follow,
            updated_field=None,
            is_finished=is_finished,
            full_contract_data=content,
            chat_history=new_chat_history
        )
    
    # 5) 정상적인 폼 답변 처리
    
    # AI 데이터 적용
    new_fields = ai_result.get("filled_fields", {})
    
    # -----------------------------------------------------------
    # ❗️ [핵심 수정] DB 저장 전 '널 문자(\u0000)' 제거 (Sanitization)
    # -----------------------------------------------------------
    # PostgreSQL은 텍스트 필드에 \u0000(Null Byte)을 저장할 수 없어 에러가 발생합니다.
    # AI가 가끔 이런 문자를 뱉을 때를 대비해 강제로 지워줍니다.
    cleaned_fields = {}
    for key, value in new_fields.items():
        if isinstance(value, str):
            # 널 문자를 빈 문자열로 치환
            cleaned_fields[key] = value.replace("\x00", "").replace("\u0000", "")
        else:
            cleaned_fields[key] = value
    
    new_fields = cleaned_fields
    content.update(new_fields)
    
    # 스킵 로직 (filled_fields가 처리하므로 skip_n은 보통 0이어야 함)
    skip_n = ai_result.get("skip_next_n_questions", 0)
    for _ in range(skip_n):
        _, idx = find_next_question(content) 
        if idx < len(CONTRACT_SCENARIO):
            content[CONTRACT_SCENARIO[idx]["field_id"]] = ""
    
    
    # 재질문(clarify) 처리
    if ai_result.get("status") == "clarify":
        follow_up_q = ai_result["follow_up_question"]
        new_chat_history.append({"sender": "bot", "message": follow_up_q})
        
        return schemas.ChatResponse(
            reply=follow_up_q,
            updated_field=None,
            is_finished=False,
            full_contract_data=content,
            chat_history=new_chat_history
        )

    # 6) 다음 질문 찾기 및 반환
    next_item, _ = find_next_question(content)

    def make_updated_field_list(fields: Dict[str, Any]) -> Optional[List[schemas.UpdatedField]]:
        if not fields:
            return None
        lst: List[schemas.UpdatedField] = []
        for k, v in fields.items():
            lst.append(schemas.UpdatedField(field_id=k, value=v))
        return lst

    updated_field_list = make_updated_field_list(new_fields)

    if next_item:
        return schemas.ChatResponse(
            reply=next_item["question"],
            updated_field=updated_field_list,
            is_finished=False,
            full_contract_data=content,
            chat_history=new_chat_history
        )
    else:
        return schemas.ChatResponse(
            reply="모든 항목이 작성되었습니다.",
            updated_field=updated_field_list, 
            is_finished=True,
            full_contract_data=content,
            chat_history=new_chat_history
        )

# -----------------------------------------------------------
# 6. DOCX 렌더링
# -----------------------------------------------------------
# ❗️ [TODO] 임대차 계약서 템플릿 파일명으로 수정하세요.
TEMPLATE_FILE = "house.docx" 

async def render_docx(contract):
    """임대차 계약서 템플릿(.docx)을 렌더링해 DocxTemplate 객체로 반환."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(current_dir, "..", "..", "templates", TEMPLATE_FILE)
    
    print(f"📂 Using template path: {template_path}")

    if not os.path.exists(template_path):
        raise FileNotFoundError(f"❌ Template not found at {template_path}")

    doc = DocxTemplate(template_path)
    context = contract.content or {}
    
    # '__SKIPPED__' 플래그 제거 (렌더링 시 깨짐 방지)
    '''clean_context = {
        key: value 
        for key, value in context.items() 
        if value != "__SKIPPED__"
    }'''
    
    render_context = {}
    for key, value in context.items():
        if value is True:
            render_context[key] = "⊠" # Wingdings 체크박스 (Checked)
        elif value is False:
            render_context[key] = "☐" # Wingdings 체크박스 (Unchecked)
        else:
            render_context[key] = value
    doc.render(render_context)
    return doc