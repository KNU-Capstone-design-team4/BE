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
    "1. 등기부등본 확인: 계약 체결 전 반드시 등기부등본(등기사항전부증명서)을 발급받아 소유자와 임대인이 일치하는지 확인해야 합니다.",
    "2. 소유자 신분증 대조: 등기부등본상의 소유자 인적사항과 임대인의 신분증이 일치하는지 확인합니다.",
    "3. 대리인 계약 시 서류: 소유자가 아닌 대리인과 계약할 경우 위임장과 인감증명서를 반드시 요구하고 확인해야 합니다.",
    "4. 신분증 진위 여부: 정부24 또는 ARS(1382)를 통해 임대인 신분증의 진위 여부를 확인할 수 있습니다.",
    "5. 권리 관계 분석: 등기부등본의 '을구'를 통해 근저당권, 가압류 등 선순위 권리 관계를 파악해야 보증금을 지킬 수 있습니다.",
    "6. 다가구 주택 선순위 보증금: 다가구 주택의 경우, 나보다 먼저 입주한 다른 세입자들의 보증금 총액을 확인해야 합니다.",
    "7. 건축물대장 확인: 불법 건축물 여부(위반건축물)를 확인해야 전세자금대출이나 보증보험 가입 시 불이익을 피할 수 있습니다.",
    "8. 정확한 소재지 기재: 등기부등본상의 주소와 계약서상의 소재지를 토씨 하나 틀리지 않고 정확하게 기재해야 합니다.",
    "9. 임대할 부분 명시: 건물 전체가 아닌 일부를 임대할 경우 층수, 호수, 면적을 정확히 기재합니다.",
    "10. 주거용/비주거용 구분: 공부상 용도와 실제 용도가 다를 경우 실제 용도를 기준으로 계약서를 작성하는 것이 유리할 수 있습니다.",
    "11. 전세/월세 명확화: 계약 형태가 전세인지 월세인지 체크박스 또는 텍스트로 명확히 표시합니다.",
    "12. 금액 한글/숫자 병기: 보증금과 차임(월세) 금액은 한글과 숫자를 함께 기재합니다.",
    "13. 계약금 비율: 통상 보증금의 5~10%를 계약금으로 설정하며, 지급 시 영수증을 받습니다.",
    "14. 중도금 지급 약정: 중도금 지급 시기(날짜)를 명확히 기재하고, 지급 후에는 임대인이 일방적으로 해제할 수 없습니다.",
    "15. 잔금 지급일: 잔금은 입주와 동시에 지급하는 것이 원칙이며 날짜를 명확히 기재합니다.",
    "16. 차임 지급 시기: 월세의 경우 선불/후불 여부와 매월 지급일을 구체적으로 정합니다.",
    "17. 계좌 이체 원칙: 보증금·월세는 반드시 임대인 명의 계좌로 이체하여 기록을 남깁니다.",
    "18. 임대차 기간 명시: 시작일과 종료일을 정확한 날짜로 기재합니다.",
    "19. 최단 존속 기간: 2년 미만으로 정해도 임차인은 2년을 주장할 수 있습니다(주임법 제4조).",
    "20. 묵시적 갱신: 만료 6개월~2개월 전 갱신 거절이 없으면 동일조건으로 갱신됩니다(주임법 제6조).",
    "21. 계약갱신요구권: 임차인은 1회에 한해 2년 갱신을 요구할 수 있습니다(주임법 제6조의3).",
    "22. 사용·수익 상태 제공: 임대인은 목적물을 사용·수익할 수 있는 상태로 인도해야 합니다.",
    "23. 선관주의 의무: 임차인은 선량한 관리자의 주의로 주택을 보존해야 합니다.",
    "24. 용도 외 사용 금지: 구조 변경 또는 용도 변경은 임대인 동의 없이는 불가합니다.",
    "25. 전대차 제한: 임차인은 임대인의 동의 없이 전대하거나 양도할 수 없습니다.",
    "26. 수선 유지 의무: 주요 설비 수리는 임대인, 소모품 교체는 임차인의 의무입니다.",
    "27. 차임 연체로 인한 해지: 2기 연체 시 임대인은 즉시 해지할 수 있습니다.",
    "28. 중도 해지: 원칙적으로 중도 해지는 불가하며, 합의 해지 시 중개수수료 부담을 특약으로 정합니다.",
    "29. 원상회복 의무: 계약 종료 시 임차인은 원상회복 후 반환해야 합니다.",
    "30. 보증금 반환 동시이행: 보증금 반환과 주택 반환은 동시에 이루어져야 합니다.",
    "31. 배액 배상: 임대인이 중도금 지급 전 계약을 해제하려면 계약금의 배액을 반환해야 합니다.",
    "32. 계약금 포기: 임차인이 중도금 지급 전 계약을 해제하려면 계약금을 포기해야 합니다.",
    "33. 근저당 말소 특약: 잔금 지급 시까지 근저당권 말소 또는 잔금일 익일까지 등기 상태 유지 특약을 넣습니다.",
    "34. 전세자금대출 특약: 대출 불가 시 계약 무효 및 계약금 반환 특약을 기재합니다.",
    "35. 장기수선충당금: 임차인이 대납하고 퇴거 시 임대인이 정산하여 반환하는 방식으로 특약을 둡니다.",
    "36. 반려동물 특약: 사육 가능 여부와 원상복구 범위를 구체적으로 기재합니다.",
    "37. 입주 청소/도배/장판: 시공 여부 및 비용 부담 주체를 특약에 명시합니다.",
    "38. 옵션 상태 확인: 옵션 품목의 작동 여부 확인 및 수리 책임 범위를 정합니다.",
    "39. 공과금 정산: 입주 전 공과금은 임대인이, 입주 후는 임차인이 부담함을 명시합니다.",
    "40. 대리인 계약 특약: “소유자 OOO의 대리인 OOO와의 계약임”을 특약에 명시합니다.",
    "41. 주택 인도: 이사(점유)를 해야 대항력이 발생합니다.",
    "42. 전입신고: 이사 당일 전입신고해야 다음 날 0시부터 대항력이 생깁니다.",
    "43. 확정일자: 계약 직후 확정일자를 받아야 우선변제권을 확보합니다.",
    "44. 전월세 신고제: 보증금 6천만 원 또는 월세 30만 원 초과 시 30일 내 신고해야 합니다.",
    "45. 서명 및 날인: 임대인·임차인의 이름, 주소, 주민번호를 기재하고 서명 또는 날인합니다.",
    "46. 간인: 계약서 여러 장은 간인을 하여 위조를 방지합니다.",
    "47. 연락처 교환: 실제 연락 가능한 전화번호를 계약서에 기재합니다.",
    "48. 계좌번호 기재: 보증금 반환 계좌번호를 특약 또는 하단에 기재하면 편리합니다.",
    "49. 계약서 보관: 임대인·임차인·중개사가 각각 1부씩 보관합니다.",
    "50. 분쟁 해결 기준: 명시되지 않은 사항은 민법·주임법·관례에 따릅니다.",
    "51. 대리인을 포함한 계약이라면 특약사항에 대리계약임을 명시하는 것이 좋다."
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
    
    # -----------------------------------------------------------
    # ❗️ [핵심 수정] 다음 질문을 먼저 계산
    # -----------------------------------------------------------
    next_item, _ = find_next_question(content)
    
    # 현재 질문과 다음 질문이 달라졌는지 확인 (질문 통과 여부)
    # current_item이 존재하고, next_item이 존재하며, ID가 다르면 통과한 것임
    # 또는 next_item이 None이면(완료) 통과한 것임
    is_moved_to_next = False
    if current_item:
        if next_item is None:
            is_moved_to_next = True
        elif current_item["field_id"] != next_item["field_id"]:
            is_moved_to_next = True
            
    # -----------------------------------------------------------
    # ❗️ [핵심 수정] 재질문(Clarify) 처리 조건 변경
    # -----------------------------------------------------------
    # AI가 '재질문'을 요청했더라도, 이미 조건을 충족해서 다음 질문으로 넘어갔다면(is_moved_to_next),
    # 재질문을 무시하고 다음 질문을 던집니다.
    # -----------------------------------------------------------
    if not is_moved_to_next and ai_result.get("status") == "clarify":
        follow_up_q = ai_result["follow_up_question"]
        new_chat_history.append({"sender": "bot", "message": follow_up_q})
        return schemas.ChatResponse(
            reply=follow_up_q,
            updated_field=None,
            is_finished=False,
            full_contract_data=content,
            chat_history=new_chat_history
        )
    '''
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
'''
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