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
CONTRACT_SCENARIO= [
    # 1. 당사자 정보
    {"field_id": "employer_name", "question": "먼저, 계약을 체결하는 '사업주'의 성함은 무엇인가요?"},
    {"field_id": "employee_name", "question": "이제 '근로자'의 성함은 무엇인가요?"},
    {"field_id": "business_name", "question": "고용주가 운영하는 사업체명(회사 이름)을 알려주세요.(예: (주)한빛유통)"},
    {"field_id": "business_phone", "question": "사업체의 대표 연락처(전화번호)를 입력해주세요."},
    {"field_id": "business_address", "question": "사업장의 소재지(주소)는 어디인가요?"},
    {"field_id": "employer_representative", "question": "사업주 서명란의 '대표자 성명'을 입력해주세요. (예: 홍길동)"},

    {"field_id": "employee_address", "question": "근로자의 현 주소는 어디인가요?"},
    {"field_id": "employee_phone", "question": "근로자의 연락처(전화번호)를 입력해주세요."},
    # 2. 계약 기간 및 장소
    {"field_id": "start_date_full", "question": "실제 근로를 시작하는 날(근로개시일)은 언제인가요? (예: 2025년 11월 1일)"},
    {"field_id": "work_location", "question": "근무하게 될 실제 장소(근무장소)를 알려주세요. (예: 사업장과 동일)"},
    {"field_id": "job_description", "question": "근로자가 수행할 업무 내용(직종)은 무엇인가요? (예: 사무 보조 및 서류 정리)"},

    # 3. 근로시간 및 휴일
    {"field_id": "start_time", "question": "하루 근로를 시작하는 시간(시업 시간)을 알려주세요. (예: 09:00)"},
    {"field_id": "end_time", "question": "하루 근로를 마치는 시간(종업 시간)을 알려주세요. (예: 18:00)"},
    {"field_id": "rest_time", "question": "휴게 시간은 몇 시부터 몇 시까지인가요? (예: 12:00 - 13:00)"},
    {"field_id": "work_day", "question": "일주일에 '총 몇 일'을 근무하나요? (숫자만 입력, 예: 5)"},
    {"field_id": "Weekly_Paid_Holiday", "question": "주휴일(유급휴일)로 지정된 요일은 무엇인가요? (예: 매주 일요일)"},

    # 4. 임금 (급여)
    {"field_id": "salary_amount", "question": "월(일, 시간)급 총 임금액을 숫자로만 알려주세요. (예: 2500000)"},
    {"field_id": "bonus", "question": "별도로 정기적인 상여금이 지급되나요?"},
    {"field_id": "bonus_amount", "question": "상여금은 얼마인가요?"},
    
    {"field_id": "allowance", "question": "상여금 외 기타 급여(제수당 등)가 지급되나요? (예: 있음/없음)"},
    {"field_id": "other_allowance_1", "question": "기타 급여 첫 번째 항목과 금액을 알려주세요. (없으면 '없음' 입력)"},
    {"field_id": "other_allowance_2", "question": "기타 급여 두 번째 항목과 금액을 알려주세요. (없으면 '없음' 입력)"},
    {"field_id": "other_allowance_3", "question": "기타 급여 세 번째 항목과 금액을 알려주세요. (없으면 '없음' 입력)"},
    {"field_id": "other_allowance_4", "question": "기타 급여 네 번째 항목과 금액을 알려주세요. (없으면 '없음' 입력)"},

    {"field_id": "salary_payment_date", "question": "임금은 매월 며칠에 지급되나요? (숫자만 입력, 예: 25)"},
    {"field_id": "payment_method", "question": "임금 지급 방법은 '계좌이체'인가요, '직접 현금 지급'인가요?"},
    
    # 5. 사회보험
    {"field_id": "employment_insurance", "question": "고용보험에 가입하나요? (예: 예/아니오)"},
    {"field_id": "industrial_accident_insurance", "question": "산재보험에 가입하나요? (예: 예/아니오)"},
    {"field_id": "national_pension", "question": "국민연금에 가입하나요? (예: 예/아니오)"},
    {"field_id": "health_insurance", "question": "건강보험에 가입하나요? (예: 예/아니오)"},

    # 11. 계약일
    {"field_id": "contract_date_full", "question": "이 근로계약서를 최종적으로 작성한 날짜는 언제인가요? (예: 2025년 10월 20일)"},

]

TIP_LIST = [
    # --- 기존 1~21번 ---
    "1. (초과근무 합의) 법정근로시간(주 40시간)을 초과하여 근무하려면, 반드시 근로자와의 서면 합의가 필요합니다. 구두 합의는 추후 분쟁의 소지가 될 수 있습니다.",
    "2. (청소년 근로) 만 18세 미만 청소년의 법정근로시간은 하루 7시간, 주 35시간을 초과할 수 없으며, 본인이 동의해도 연장근로는 주 5시간까지만 가능합니다.",
    "3. (휴일근로수당) 휴일에 근무했다면 반드시 가산수당을 받아야 합니다. 8시간 이내 근무는 통상임금의 1.5배, 8시간을 초과한 근무는 2배를 지급받아야 합니다.",
    "4. (야간근로수당) 오후 10시부터 다음 날 오전 6시 사이에 근무했다면, 통상임금의 50%를 야간근로수당으로 추가 지급받아야 합니다.",
    "5. (수당 중복지급) 만약 휴일에 야간 근무를 했다면, 휴일근로수당(1.5배)과 야간근로수당(0.5배)이 중복으로 적용되어 통상임금의 2배를 받을 수 있습니다.",
    "6. (주휴수당 조건) 주휴수당은 '1주 소정근로시간 15시간 이상'과 '1주 개근'이라는 두 가지 조건을 모두 충족해야 발생합니다.",
    "7. (단기 근로자 주휴수당) 계약 기간이 1주일이라도, 주 15시간 이상 일하고 개근했다면 계약 종료와 별개로 주휴수당을 지급받을 수 있습니다. 다음 주 근무 여부는 상관없습니다.",
    "8. (계약서 작성 시점) 모든 근로계약서는 반드시 업무를 시작하기 전에 작성해야 하며, 작성 후 1부를 근로자에게 즉시 교부하는 것이 법적 의무입니다.",
    "9. (계약서 미작성 벌금) 근로계약서를 서면으로 작성하고 교부하지 않은 경우, 사업주는 500만원 이하의 벌금에 처해질 수 있습니다.",
    "10. (근로조건 변경) 임금, 근로시간 등 중요한 근로조건이 변경될 경우, 구두 합의만으로는 부족하며 반드시 변경된 내용을 서면으로 명시하여 다시 교부해야 합니다.",
    "11. (단시간 근로자 계약서) 아르바이트처럼 근무 요일이나 시간이 유동적인 경우, \"월, 수, 금, 14:00~18:00\"와 같이 근로일과 근로일별 근로시간을 반드시 구체적으로 명시해야 합니다.",
    "12. (휴게시간 명시) 휴게시간은 임금에 포함되지 않는 무급 시간이 원칙입니다. 따라서 계약서에 휴게시간을 명확히 기재해야 총 근로시간 및 임금 계산에 대한 오해를 막을 수 있습니다.",
    "13. (휴게시간 법적 기준) 근로시간이 4시간이면 30분 이상, 8시간이면 1시간 이상의 휴게시간을 '근로시간 도중에' 부여해야 합니다. 업무 시작 전이나 종료 후에 부여하는 것은 위법입니다.",
    "14. (퇴직금 연봉 포함 금지) 월급이나 연봉에 퇴직금을 포함하여 지급하는 계약은 근로기준법상 불법이며 무효입니다. 퇴직금은 반드시 퇴직 시점에 별도로 정산받아야 합니다.",
    "15. (포괄임금제 유의사항) 연장·야간수당 등을 미리 월급에 포함하는 포괄임금제 계약은 가능하지만, 실제 발생한 수당이 약정된 수당보다 많을 경우 차액을 추가로 지급해야 합니다.",
    "16. (공휴일 유급휴일) 2022년부터 사업장 규모와 상관없이 모든 근로자는 '빨간 날'(관공서 공휴일)을 유급휴일로 보장받아야 합니다.",
    "17. (대체휴일 적용) 공휴일이 주말과 겹치는 경우 발생하는 대체공휴일 역시 모든 사업장에서 유급휴일로 보장해야 합니다.",
    "18. (휴일 조항 명시) 근로계약서에는 '주휴일'이 무슨 요일인지, '공휴일'을 유급으로 보장하는지 등 휴일에 관한 사항을 반드시 포함해야 합니다.",
    "19. (5인 미만 사업장 예외) 연장·야간·휴일근로 가산수당, 연차유급휴가 등의 일부 규정은 상시 근로자 5인 미만 사업장에는 적용되지 않을 수 있으니 확인이 필요합니다.",
    "20. (벌금과 별개로 임금 지급 의무) 사업주가 근로기준법 위반으로 벌금을 내더라도, 근로자에게 지급해야 할 주휴수당, 가산수당 등의 임금 지급 의무는 사라지지 않습니다.",
    "21. (최저시급) 올해(2025년)을 기준으로 최저시급은 10,030원입니다. 이를 지키지 않을 경우, 3년 이하의 징역 또는 2천만원 이하의 벌금에 처할 수 있습니다.",
    "22. (수습기간 급여) 1년 이상 근로계약을 체결한 경우에만 수습기간(최대 3개월) 동안 최저임금의 90%를 지급할 수 있습니다. 1년 미만 계약자는 수습기간에도 최저임금 100%를 지급해야 합니다.",
    "23. (단순노무직 수습 감액 금지) 편의점, 식당 서빙, 주유원 등 단순노무직종 종사자는 수습기간이라 하더라도 최저임금을 감액할 수 없습니다.",
    "24. (해고예고) 사용자가 근로자를 해고하려면 적어도 30일 전에 예고해야 합니다. 30일 전에 예고하지 않았을 경우 30일분 이상의 통상임금(해고예고수당)을 지급해야 합니다.",
    "25. (해고예고 예외) 근로자가 계속 근로한 기간이 3개월 미만인 경우, 해고예고 없이 즉시 해고할 수 있으며 해고예고수당 지급 의무도 없습니다.",
    "26. (해고 서면 통지) 5인 이상 사업장의 경우, 사용자는 해고 사유와 해고 시기를 반드시 '서면'으로 통지해야 효력이 발생합니다. 문자나 카톡 해고 통보는 무효가 될 수 있습니다.",
    "27. (부당해고 구제신청) 상시 근로자 5인 이상 사업장에서 정당한 이유 없이 해고당했다면, 해고일로부터 3개월 이내에 노동위원회에 부당해고 구제신청을 할 수 있습니다.",
    "28. (임금명세서 교부 의무) 2021년 11월부터 사업장 규모와 상관없이 사용자는 근로자에게 임금의 구성항목, 계산방법, 공제내역이 적힌 임금명세서를 매월 교부해야 합니다.",
    "29. (연차 유급휴가 발생) 1년간 80% 이상 출근한 근로자에게는 15일의 유급휴가를 주어야 합니다. (5인 이상 사업장 적용)",
    "30. (신입사원 연차) 근로 기간이 1년 미만인 근로자 또는 1년간 80% 미만 출근한 근로자에게는 1개월 개근 시 1일의 유급휴가를 주어야 합니다.",
    "31. (연차 미사용 수당) 근로자가 발생한 연차를 1년 동안 사용하지 못하고 소멸된 경우, 남은 일수만큼 연차 미사용 수당(돈)으로 청구할 권리가 있습니다.",
    "32. (4대보험 의무 가입) 월 소정근로시간이 60시간 이상인 근로자는 고용보험, 산재보험, 국민연금, 건강보험 등 4대보험 가입 의무 대상입니다.",
    "33. (초단시간 근로자 4대보험) 주 15시간 미만(월 60시간 미만) 근로자라도 '산재보험'과 '고용보험(3개월 이상 근무 시)'은 가입해야 합니다.",
    "34. (퇴직금 지급 기한) 근로자가 퇴직한 경우, 당사자 간 합의가 없다면 지급 사유가 발생한 날(퇴직일)로부터 14일 이내에 퇴직금을 지급해야 합니다.",
    "35. (퇴직금 중간정산) 퇴직금은 원칙적으로 퇴직할 때 지급하는 것이며, 주택 구입이나 요양 등 법에서 정한 특별한 사유 없이는 재직 중에 미리 정산(중간정산)할 수 없습니다.",
    "36. (출산전후 휴가) 임신 중인 여성 근로자는 출산 전과 출산 후를 합하여 총 90일(다태아 120일)의 출산전후 휴가를 받을 수 있으며, 출산 후에 45일 이상이 배정되어야 합니다.",
    "37. (육아휴직) 만 8세 이하 또는 초등학교 2학년 이하의 자녀가 있는 남녀 근로자는 최대 1년(부모 각각 1년)의 육아휴직을 신청할 수 있습니다.",
    "38. (배우자 출산휴가) 남성 근로자는 배우자가 출산했을 때 10일의 유급휴가를 청구할 수 있습니다. 출산한 날부터 90일 이내에 청구해야 합니다.",
    "39. (생리휴가) 여성 근로자가 청구하는 경우 월 1일의 생리휴가를 주어야 합니다. 이는 무급이 원칙이나, 회사 내규로 유급으로 정할 수도 있습니다.",
    "40. (휴업수당) 사용자의 귀책사유(경영 악화 등)로 휴업하는 경우, 사용자는 휴업 기간 동안 근로자에게 평균임금의 70% 이상을 수당으로 지급해야 합니다. (5인 이상 사업장)",
    "41. (근로계약 불이행 손해배상 금지) 근로계약서에 '중도 퇴사 시 위약금 100만원 배상'과 같이 근로계약 불이행에 대한 위약금이나 손해배상액을 미리 정해놓는 것은 불법입니다.",
    "42. (전차금 상계 금지) 사용자는 근로자에게 빌려준 돈(전차금)이 있다고 해서 이를 일방적으로 월급에서 공제(상계)하고 지급할 수 없습니다. 월급은 전액 지급해야 합니다.",
    "43. (강제 근로 금지) 사용자는 폭행, 협박, 감금, 그 밖의 정신상 또는 신체상의 자유를 부당하게 구속하는 수단으로 근로자의 자유의사에 어긋나는 근로를 강요할 수 없습니다.",
    "44. (직장 내 괴롭힘 금지) 사용자 또는 근로자는 직장에서의 지위나 관계 등의 우위를 이용하여, 업무상 적정범위를 넘어 다른 근로자에게 신체적·정신적 고통을 주거나 근무환경을 악화시키는 행위를 해서는 안 됩니다.",
    "45. (산업재해 신청) 업무상 사유로 부상을 당하거나 질병에 걸린 경우, 근로복지공단에 산재 신청을 할 수 있습니다. 사용자가 산재 처리를 거부하더라도 근로자가 직접 신청 가능합니다.",
    "46. (임금채권 소멸시효) 임금, 퇴직금, 각종 수당 등을 받을 권리는 3년간 행사하지 않으면 소멸시효가 완성되어 더 이상 청구할 수 없습니다.",
    "47. (기간제 근로자 차별 금지) 기간제(계약직) 근로자임을 이유로 동종·유사 업무에 종사하는 정규직 근로자에 비해 임금, 복리후생 등에서 합리적 이유 없이 불리하게 처우해서는 안 됩니다.",
    "48. (계약기간 제한) 기간제 근로자의 사용 기간은 원칙적으로 2년을 초과할 수 없습니다. 2년을 초과하여 사용하는 경우, 기간의 정함이 없는 근로계약(무기계약직)으로 간주됩니다.",
    "49. (사직서 수리 기간) 근로자가 사직서를 제출했으나 사용자가 이를 수리하지 않는 경우, 민법상 사직서 제출일로부터 1개월(또는 다음 임금지급기)이 지나면 자동으로 사직의 효력이 발생합니다.",
    "50. (사용증명서 발급) 사용자는 근로자가 퇴직한 후라도 사용 기간, 업무 종류, 지위와 임금, 그 밖의 사항에 관한 증명서(경력증명서)를 청구하면 사실대로 적어 즉시 내주어야 합니다."
]

def calculate_work_hours(start_str: str, end_str: str) -> float:
    try:
        # 혹시 모를 공백 제거
        start_str = start_str.strip()
        end_str = end_str.strip()
        
        fmt = "%H:%M"
        t_start = datetime.datetime.strptime(start_str, fmt)
        t_end = datetime.datetime.strptime(end_str, fmt)
        
        if t_end < t_start:
            t_end += datetime.timedelta(days=1)
            
        diff = t_end - t_start
        return diff.total_seconds() / 3600
    except Exception as e:
        print(f"Date Calc Error: {e}") # 에러 로그 출력
        return 0.0

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
    embeddings = await get_tip_embeddings()
    q_emb = await get_embedding(question)
    sims = [np.dot(q_emb, t) for t in embeddings]

    idx = np.argsort(sims)[-top_n:][::-1]
    top_score = sims[idx[0]]
    tips_str = "\n".join([TIP_LIST[i] for i in idx])
    return tips_str, top_score

async def get_rag_response(question: str, relevant_tips: str) -> str:
    today = datetime.date.today()
    current_date_str = today.strftime('%Y년 %m월 %d일')
    system_prompt = f"""
    오늘은 {current_date_str}입니다.
    당신은 '근로계약 전문가 AI 상담관'입니다.
    
    [답변 생성 규칙]
    1. 아래 제공된 [참고 자료]를 **최우선**으로 검토하여 답변을 생성하세요.
    2. 질문의 내용이 [참고 자료]에 명확히 포함되어 있다면, 그 내용을 바탕으로 신뢰성 있게 답변하세요.
    3. 만약 질문 내용이 [참고 자료]에 없다면, 당신이 가진 일반적인 AI 지식을 활용하여 답변하세요.
       단, 이 경우 **반드시 답변의 맨 뒤에 아래 문구를 붙여야 합니다.**
       
       "[참고 자료에 없는 내용입니다. 일반적인 AI 지식에 기반하여 답변합니다.]"

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
        - 체크박스 ☐ 를 채울 땐: "☑" (U+2612) 또는 "☐" (U+2610)
        - 날짜 형식은 "YYYY년 MM월 DD일" (예: "2025년 03월 07일")
        - 시간 형식은 24시간제 "HH:MM" (예: "09:00", "14:30")
    4.  `skip_next_n_questions`는 '없음'을 선택하여 다음 질문이 불필요할 때 사용됩니다.
    5.  반드시 지정된 JSON 형식으로만 반환해야 합니다.
    6. 답변이 원하는 대답이 아니면 다시 질문하고 원하는 답이 나오면 그 답을 변수에 채워넣습니다.
    7. `bonus_amount` 등 금액을 나타내는 필드에는 단위(예: 원, 만원)을 지우고 숫자 및 쉼표만 입력합니다. (예: "500,000")
    8. 성명(이름)을 묻는 질문에는 사용자가 '홍길', '이 산' 처럼 2글자나 외자 이름을 입력하더라도, 오타가 명확하지 않다면 그대로 추출하세요. 되묻지 마십시오.
    9. 참고 자료에 없는 내용은 언급하지 마십시오. (예: "2023년 정보는 없습니다" 같은 말 금지)
    10.만약 사용자가 정보를 입력하는 대신 **"최저시급이 얼마야?", "주휴수당 조건이 뭐야?", "4대보험 꼭 해야해?"** 처럼
       법률적인 정보나 일반적인 지식을 묻는 질문(Question)을 한다면, 
       즉시 `status: "rag_required"`를 반환하십시오. 이때 `filled_fields`는 비워둡니다.
    11.시간 형식에 13이상의 숫자가 들어오면 24시간제로 인식하고 유지하세요.

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
    elif field_id == "rest_time":
        specific_examples = f"""
        [예시 1: '12:00 - 13:00' (시간 범위)]
        question: "{question}"
        user_message: "12시부터 1시까지요"
        # 1시(13:00) - 12시(12:00) = 60분
        AI: {{"status": "success", "filled_fields": {{"rest_time": "60"}}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 2: '60분' (분 명시)]
        question: "{question}"
        user_message: "총 60분입니다"
        AI: {{"status": "success", "filled_fields": {{"rest_time": "60"}}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 3: '1시간' (시간 명시)]
        question: "{question}"
        user_message: "1시간이요"
        AI: {{"status": "success", "filled_fields": {{"rest_time": "60"}}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 4: '1시간 30분']
        question: "{question}"
        user_message: "1시간 30분입니다"
        AI: {{"status": "success", "filled_fields": {{"rest_time": "90"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """

    elif field_id in ["start_time", "end_time"]:
        specific_examples = f"""
        [규칙]
        1. 입력된 시간을 무조건 'HH:MM' (24시간제) 형식으로 변환하여 저장하세요.
        2. '오후', '저녁', '밤' 키워드가 있거나 13 이상의 숫자는 24시간제로 변환하세요.
        3. ⭐️ 중요: 근무 시작 시간이 오후(13시~)나 밤이어도 절대 이상하다고 생각하거나 되묻지 마세요. (야간/교대 근무 가능)
        4. 사용자가 입력한 그대로를 믿고 변환만 수행하세요.
        
        [예시 1: '18시' -> 그대로 18:00 저장 (되묻기 금지)]
        question: "{question}"
        user_message: "18시"
        AI: {{"status": "success", "filled_fields": {{"{field_id}": "18:00"}}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 2: '오후 6시' -> 18:00 저장]
        question: "{question}"
        user_message: "오후 6시요."
        AI: {{"status": "success", "filled_fields": {{"{field_id}": "18:00"}}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 3: '밤 10시' -> 22:00 저장]
        question: "{question}"
        user_message: "밤 10시에 시작해요"
        AI: {{"status": "success", "filled_fields": {{"{field_id}": "22:00"}}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 4: '09:00' -> 그대로 저장]
        question: "{question}"
        user_message: "09:00"
        AI: {{"status": "success", "filled_fields": {{"{field_id}": "09:00"}}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 5: '2시' -> 모호함 -> **되묻기**]
        question: "{question}"
        user_message: "2시에 시작해요"
        AI: {{"status": "clarify", "filled_fields": {{}}, "skip_next_n_questions": 0, "follow_up_question": "말씀하신 2시가 '오후 2시(14:00)'인가요, 아니면 '새벽 2시(02:00)'인가요?"}}

        [예시 6: '10시' -> 모호함 -> **되묻기**]
        question: "{question}"
        user_message: "10시요"
        AI: {{"status": "clarify", "filled_fields": {{}}, "skip_next_n_questions": 0, "follow_up_question": "오전 10시인가요, 밤 10시(22:00)인가요?"}}
        """
        
    # [상여금] 예시
    elif field_id == "bonus":
        specific_examples = f"""
        [예시 1: '있음' 선택 (금액 입력)]
        question: "{question}"
        user_message: "네 100만원이요"
        AI: {{"status": "success", "filled_fields": {{
            "bonus_amount": "1,000,000",
            "bonus_yes": true,           /* HTML '있음' 체크 해제 */
            "bonus_none": false,           /* HTML '없음' 체크 */
            "is_bonus_paid_yes_o": "O",
            "is_bonus_paid_no_o": " "
        }}, "skip_next_n_questions": 0, "follow_up_question": null}}

       [예시 2: '있음'만 답변 (금액 미포함) -> ⭐️ 금액 필드 제거/비움]
        question: "{question}"
        user_message: "네 지급됩니다"
        AI: {{"status": "success", "filled_fields": {{
            "bonus_yes": true,
            "bonus_none": false,
            "is_bonus_paid_yes_o": "O",
            "is_bonus_paid_no_o": " "
            // ⭐️ bonus_amount를 비워둠 -> 그래야 다음 질문(금액)이 나옴
        }}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 3: '없음' 선택]
        question: "{question}"
        user_message: "아니요 없습니다"
        AI: {{"status": "success", "filled_fields": {{
            "bonus_amount": "",
            "bonus_yes": false, /* HTML '있음' 체크 해제 */
            "bonus_none": true, /* HTML '없음' 체크 */
            "is_bonus_paid_yes_o": " ",
            "is_bonus_paid_no_o": "O"
        }}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 4: '없음' 선택 (단답형/반말 - '아니.', '없어')]
        question: "{question}"
        user_message: "아니."
        AI: {{"status": "success", "filled_fields": {{
            "bonus_amount": "",
            "bonus_yes": false,
            "bonus_none": true,
            "is_bonus_paid_yes_o": " ",
            "is_bonus_paid_no_o": "O"
        }}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """
    
    elif field_id == "bonus_amount": # ⭐️ 여기를 이렇게 고치세요!
        specific_examples = f"""
        [규칙]
        1.금액이 입력되면 '상여금 있음'으로 간주하고 관련 체크박스(is_bonus_paid_yes_o)도 함께 "O"로 설정하세요.
        2. 사용자가 '30000', '500000' 처럼 숫자만 입력해도 즉시 금액으로 인식하고 저장하세요.
        3. 단위(원, 만원)가 없어도 숫자가 포함되어 있으면 금액으로 간주합니다.
        4. 금액이 입력되면 자동으로 **'상여금 있음' 체크박스(is_bonus_paid_yes_o)를 "O"로 설정하세요.
        5. 정보가 충분하므로 절대 되묻지 말고 `status: "success"`를 반환하세요.
        6. 사용자가 '30000', '50만' 처럼 **숫자만 입력하더라도** 즉시 금액으로 인식하고 '성공(success)' 처리하십시오.
        7. 절대 "상여금이 지급되나요?" 또는 "있음/없음으로 대답해주세요"라고 **되묻지 마십시오.**
        
        [예시 1: 숫자만 입력된 경우 (핵심)]
        question: "{question}"
        user_message: "30000"
        AI: {{"status": "success", "filled_fields": {{
            "bonus_amount": "30,000",
            "bonus_yes": true,
            "bonus_none": false,
            "is_bonus_paid_yes_o": "O", 
            "is_bonus_paid_no_o": " "
        }}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 2: 금액 입력 -> 금액 + '있음' 체크 동시 수행]
        question: "{question}"
        user_message: "50만원입니다"
        AI: {{"status": "success", "filled_fields": {{
            "bonus_amount": "500,000",
            "bonus_yes": true,
            "bonus_none": false,
            "is_bonus_paid_yes_o": "O", 
            "is_bonus_paid_no_o": " "
        }}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 3: 금액 입력 (단위 생략)]
        question: "{question}"
        user_message: "1200000"
        AI: {{"status": "success", "filled_fields": {{
            "bonus_amount": "1,200,000",
            "bonus_yes": true,
            "bonus_none": false,
            "is_bonus_paid_yes_o": "O", 
            "is_bonus_paid_no_o": " "
        }}, "skip_next_n_questions": 0, "follow_up_question": null}}

        """
    
    elif field_id == "Weekly_Paid_Holiday":
        specific_examples = f"""
        [예시 1: 요일 입력 (성공)]
        question: "{question}"
        user_message: "매주 일요일로 정했습니다."
        AI: {{"status": "success", "filled_fields": {{"Weekly_Paid_Holiday": "일"}}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 2: 공백 입력 (없음)]
        question: "{question}"
        user_message: "주휴일은 따로 없습니다."
        AI: {{"status": "success", "filled_fields": {{"Weekly_Paid_Holiday": ""}}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 3: 공백 입력 (없음 - 단답형)]
        question: "{question}"
        user_message: "없습니다" 
        AI: {{"status": "success", "filled_fields": {{"Weekly_Paid_Holiday": ""}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """

    # [기타급여] 예시
    elif field_id == "allowance":
        specific_examples = f"""
        [예시 1: '있음' 선택 (다음 질문으로 이동)]
        question: "상여금 외 기타 급여(제수당 등)가 지급되나요? (예: 있음/없음)"
        user_message: "네 있습니다"
        AI: {{"status": "success", "filled_fields": {{
            "allowance_yes": true,        /* HTML '있음' 체크 */
            "other_allowance_none": false,  /* HTML '없음' 체크 해제 */
            "is_allowance_paid_yes_o": "O",
            "is_allowance_paid_no_o": " "
        }}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 2: '없음' 선택 (다음 4개 질문 스킵)]
        question: "상여금 외 기타 급여(제수당 등)가 지급되나요? (예: 있음/없음)"
        user_message: "아니요 없어요"
        AI: {{"status": "success", "filled_fields": {{
            "allowance_yes": false,       /* HTML '있음' 체크 해제 */
            "other_allowance_none": true,   /* HTML '없음' 체크 */
            "is_allowance_paid_yes_o": " ",
            "is_allowance_paid_no_o": "O",
            "other_allowance_1": "", 
            "other_allowance_2": "", 
            "other_allowance_3": "", 
            "other_allowance_4": ""
        }}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """
    elif field_id.startswith("other_allowance_"):
        # 현재 field_id에서 숫자 추출 (예: "other_allowance_2" -> 2)
        try:
            current_num = int(field_id.split('_')[-1]) # 1, 2, 3, 4
        except ValueError:
            current_num = 1 # 기본값

        # '없음' 선택 시 스킵할 질문 수 계산 (남은 질문 수)
        skip_count = 4 - current_num

        # '없음' 선택 시 미리 채워둘 필드 생성
        # 예: 2번에서 '없음' -> {"other_allowance_2": "", "other_allowance_3": "", "other_allowance_4": ""}
        fields_to_fill_on_none = {}
        for i in range(current_num, 5): # current_num 부터 4까지
            fields_to_fill_on_none[f"other_allowance_{i}"] = ""
        
        filled_fields_str = str(fields_to_fill_on_none).replace("'", '"')

        specific_examples = f"""
        [예시 1: '있음' (항목 + 금액) -> 성공]
        question: "{question}"
        user_message: "네 식대 10만원이요"
        AI: {{"status": "success", "filled_fields": {{"{field_id}": "식대 100,000원"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        
        [예시 2: '있음' (금액만 입력) -> 되묻기 (항목) **⭐️ 금액 저장**]
        question: "{question}"
        user_message: "100000"
        AI: {{"status": "clarify", "filled_fields": {{"{field_id}_amount_temp": "100,000원"}}, "skip_next_n_questions": 0, "follow_up_question": "금액 100,000원의 항목(종류)은 무엇인가요? (예: 식대, 교통비)"}}

        [예시 3: '있음' (항목만 입력) -> 되묻기 (금액) **⭐️ 항목 저장**]
        question: "{question}"
        user_message: "교통비"
        AI: {{"status": "clarify", "filled_fields": {{**"{field_id}_item_temp": "교통비"**}}, "skip_next_n_questions": 0, "follow_up_question": "교통비의 금액은 얼마인가요? (예: 50000원)"}}

        [예시 4: '있음' (모호한 단위) -> 되묻기 (항목) **⭐️ 금액 저장**]
        question: "{question}"
        user_message: "15만원입니다"
        AI: {{"status": "clarify", "filled_fields": {{"{field_id}_amount_temp": "150,000원"}}, "skip_next_n_questions": 0, "follow_up_question": "금액 15만원의 항목(종류)은 무엇인가요? (예: 식대, 교통비)"}}

        [예시 5: '없음' 선택 (현재 + 나머지 공백 저장 및 스킵)]
        question: "{question}"
        user_message: "아니요 없어요"
        AI: {{"status": "success", "filled_fields": {filled_fields_str}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """

    # [지급방법] 예시
    elif field_id == "payment_method":
        specific_examples = """
        [예시 1: '계좌이체' 선택]
        question: "임금 지급 방법은 '계좌이체'인가요, '직접 현금 지급'인가요?"
        user_message: "통장으로 받을게요"
        AI: {{"status": "success", "filled_fields": {{
            "direct_pay": false, 
            "bank_pay": true,
            "payment_method_direct_o": " ",
            "payment_method_bank_o": "O"
        }}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 2: '직접 지급' 선택]
        question: "임금 지급 방법은 '계좌이체'인가요, '직접 현금 지급'인가요?"
        user_message: "현금으로 직접 받고 싶어요"
        AI: {{"status": "success", "filled_fields": {{
            "direct_pay": true, 
            "bank_pay": false,
            "payment_method_direct_o": "O",
            "payment_method_bank_o": " "
        }}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """
    
    # [사회보험] 예시
    elif field_id in ["employment_insurance", "industrial_accident_insurance", "national_pension", "health_insurance"]:
        # DOCX용 변수명 (예: apply_employment_insurance_check)
        check_variable_name = f"apply_{field_id}_check" 
        
        specific_examples = f"""
        [예시 1: '예' 선택 (HTML: true, DOCX: ☒)]
        question: "{question}"
        user_message: "네 가입해요"
        AI: {{"status": "success", "filled_fields": {{
            "{field_id}": true,
            "{check_variable_name}": "☑"
        }}, "skip_next_n_questions": 0, "follow_up_question": null}}
        
        [예시 2: '아니오' 선택 (HTML: false, DOCX: ☐)]
        question: "{question}"
        user_message: "아니요"
        AI: {{"status": "success", "filled_fields": {{
            "{field_id}": false,
            "{check_variable_name}": "☐"
        }}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """
    
    # [기본] 예시
    else: 
        specific_examples = f"""
        [예시 1: 일반 텍스트 추출]
        question: "{question}"
        user_message: "저희 회사는 (주)한빛유통입니다."
        AI: {{"status": "success", "filled_fields": {{"{field_id}": "(주)한빛유통"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        
        [예시 2: 시간 형식화 (오전)]
        question: "하루 근로를 시작하는 시간(시업 시간)을 알려주세요. (예: 09:00)"
        user_message: "9시입니다."
        AI: {{"status": "success", "filled_fields": {{"start_time": "09:00"}}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 3: 시간 형식화 (오후)]
        question: "하루 근로를 마치는 시간(종업 시간)을 알려주세요. (예: 18:00)"
        user_message: "저녁 6시요."
        AI: {{"status": "success", "filled_fields": {{"end_time": "18:00"}}, "skip_next_n_questions": 0, "follow_up_question": null}}  
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
        if field_id == "bonus":
            if "is_bonus_paid_yes_o" in current_content or "is_bonus_paid_no_o" in current_content:
                continue # 템플릿에 들어갈 O/X 표시가 있으면 완료된 것임

        if field_id == "bonus_amount":
            # 상여금 없음(No)에 체크되어 있다면 -> 금액 질문 스킵
            if current_content.get("is_bonus_paid_no_o") == "O":
                continue
            
        # 3. 기타 특수 필드 체크 (이전 로직을 is_field_completed의 논리로 변경)
        #    'is_allowance_paid' 대신 'allowance' 필드 ID를 사용해야 합니다.
        if field_id == "allowance":
             if "is_allowance_paid_yes_o" in current_content or "is_allowance_paid_no_o" in current_content:
                continue
             
        if field_id == "payment_method":
            if "payment_method_direct_o" in current_content or "payment_method_bank_o" in current_content:
                continue

        if field_id in ["employment_insurance", "industrial_accident_insurance", "national_pension", "health_insurance"]:
             check_variable_name = f"apply_{field_id}_check" 
             if check_variable_name in current_content:
                continue

        # 5. 기타 급여 항목 스킵 체크 (이전 로직에서 그대로 가져옴)
        if field_id.startswith("other_allowance_") and current_content.get("is_allowance_paid_no_o") == "O":
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

    new_chat_history = contract.chat_history.copy() if isinstance(contract.chat_history, list) else []
    
    # ✅ 1) 다음 질문 찾기
    current_item, current_index = find_next_question(content)
    
    # 이 턴(Turn)의 봇 질문을 미리 저장해둡니다. (폼 답변 시 사용)
    current_bot_question = current_item["question"] if current_item else None
    current_field_id = current_item["field_id"] if current_item else None
    
    # ✅ 2) 아무 입력 없으면 "시작/재개"
    if not message.strip() or message.strip() == "string":
        
        user_has_spoken = any(msg.get("sender") == "user" for msg in new_chat_history)

        # [케이스 A] 사용자가 아직 말을 안 함 (완전 처음) -> 질문만 던짐 (스킵 X)
        if not user_has_spoken:
            if current_item:
                return schemas.ChatResponse(
                    reply=current_item["question"],
                    updated_field=None,
                    is_finished=False,
                    full_contract_data=content,
                    chat_history=new_chat_history
                )
        
        # [케이스 B] 이미 대화 중임 + 엔터 입력 -> 현재 질문 스킵 (빈 값 저장)
        if current_item:
            # 1. 현재 질문을 빈 값("")으로 저장
            field_id = current_item["field_id"]
            content[field_id] = "" 

            # 2. 다음 질문 찾기
            next_item, _ = find_next_question(content)
            
            # 3. 스킵 안내 메시지 생성
            reply_text = f"(건너뜁니다)\n{next_item['question']}" if next_item else "모든 항목이 작성되었습니다."
            is_finished = (next_item is None)
            
            # 스킵했다는 기록도 채팅에 남기는 것이 좋습니다 (선택 사항)
            # new_chat_history.append({"sender": "user", "message": "(건너뛰기)"})
            # new_chat_history.append({"sender": "bot", "message": reply_text})

            return schemas.ChatResponse(
                reply=reply_text,
                updated_field=[{"field_id": field_id, "value": ""}],
                is_finished=is_finished,
                full_contract_data=content,
                chat_history=new_chat_history
            )
        else:
            # 이미 완료된 상태
            return schemas.ChatResponse(
                reply="모든 항목이 작성되었습니다! 추가 질문이 있나요?",
                updated_field=None,
                is_finished=True,
                full_contract_data=content,
                chat_history=new_chat_history
            )

    # 공통 채팅 기록 저장 (봇 질문이 있었을 때만 저장)
    # if current_bot_question:
    #     new_chat_history.append({"sender": "bot", "message": current_bot_question})
    
    new_chat_history.append({"sender": "user", "message": message})
    
    # -----------------------------------------------------------
    # ✅ [핵심 수정] 3) AI 추출 및 의도 파악
    # -----------------------------------------------------------
    
    # (A) 폼 작성이 이미 완료된 경우 -> 무조건 RAG 모드로 설정
    if current_item is None:
        ai = {"status": "rag_required"} 
        
    # (B) 폼 작성 중인 경우 -> AI에게 추출 시도
    else:
        ai = await get_smart_extraction(
            client,
            current_field_id, # ❗️ None이 아님이 보장됨
            message,
            current_bot_question
        )
        
    # -----------------------------------------------------------
    # ✅ [수정] 4) RAG 여부 판단 및 처리
    # -----------------------------------------------------------
    # 1. AI가 "이건 질문이다"라고 했거나 (rag_required)
    # 2. 기존 유사도 검사에서 점수가 높을 경우
    
    is_rag = False
    if ai.get("status") == "rag_required":
        is_rag = True
    else:
        # AI가 판단하지 않았더라도, 유사도가 높으면 RAG로 처리 (보조 수단)
        tips, score = await find_top_relevant_tips(message)
        if score >= SIMILARITY_THRESHOLD:
            is_rag = True

    if is_rag:
        tips, _ = await find_top_relevant_tips(message)
        rag_answer = await get_rag_response(message, tips)

        # RAG 턴 기록
        new_chat_history.append({"sender": "bot", "message": rag_answer})
        
        # 후속 멘트 처리
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
    
    
    # -----------------------------------------------------------
    # ✅ 5) 폼 답변 데이터 처리 (current_item이 있을 때만 실행)
    # -----------------------------------------------------------
    if current_item:
        # AI가 반환한 filled_fields 적용
        new_fields = ai.get("filled_fields", {})

        # [기타 급여 항목 합치기 로직]
        field_id = current_item["field_id"]
        if field_id.startswith("other_allowance_"):
            item_temp = content.get(f"{field_id}_item_temp")
            amount_temp = content.get(f"{field_id}_amount_temp")
            
            new_item = new_fields.get(f"{field_id}_item_temp")
            new_amount = new_fields.get(f"{field_id}_amount_temp")

            final_item = new_item if new_item else item_temp
            final_amount = new_amount if new_amount else amount_temp

            content.update(new_fields) 
            
            if final_item and final_amount:
                content[field_id] = f"{final_item} {final_amount}"
                content.pop(f"{field_id}_item_temp", None)
                content.pop(f"{field_id}_amount_temp", None)
                
                ai['status'] = "success" 
                new_fields.clear() 
                new_fields[field_id] = content[field_id] 
            else:
                pass
        
        content.update(new_fields)

        # skip_next_n_questions 적용
        skip_n = ai.get("skip_next_n_questions", 0)
        for _ in range(skip_n):
            _, idx = find_next_question(content)
            if idx < len(CONTRACT_SCENARIO):
                content[CONTRACT_SCENARIO[idx]["field_id"]] = ""

        # 재질문(clarify) 처리
        if ai.get("status") == "clarify":
            follow_up_q = ai["follow_up_question"]
            new_chat_history.append({"sender": "bot", "message": follow_up_q})
            
            return schemas.ChatResponse(
                reply=ai["follow_up_question"],
                updated_field=None,
                is_finished=False,
                full_contract_data=content,
                chat_history=new_chat_history
            )
        
    if "employee_name" in new_fields:
                content["employee_name_sign"] = new_fields["employee_name"]

     # ✅ 다음 질문 찾기
    next_item, _ = find_next_question(content)

    # -----------------------------------------------------------------
    # ✅ [4. CHAT HISTORY 추가]
    # updated_key는 폼 답변 성공 시에만 정의되므로, 
    # 'if next_item:' 블록 밖으로 이동시키거나 안전하게 처리합니다.
    #updated_key = list(new_fields.keys())[0] if new_fields else None
    updated_key = list(new_fields.keys())[0] if (current_item and new_fields) else None
    updated_field_list = []
    
    # 1. 키가 있고, 실제로 딕셔너리에 그 키가 존재하는지 확인 (안전장치)
    if updated_key and updated_key in new_fields:
        updated_field_list = [{
            "field_id": updated_key,
            "value": str(new_fields[updated_key]) # 안전하게 문자열 변환
        }]
    # 2. new_fields가 비어있지만 스킵 등으로 넘어가는 경우
    elif not new_fields and current_item:
         # 필요한 경우 빈 값 처리 (현재는 리스트 비워둠)
         pass

    ################################################################
    # 기본 답변 설정 (다음 질문이 있으면 질문, 없으면 완료 메시지)
    final_reply = next_item["question"] if next_item else "모든 항목이 작성되었습니다."
    
    # -----------------------------------------------------------
    # ✅ [2] 실시간 검증 & 메시지 합치기 (Validation)
    # -----------------------------------------------------------
    warning_prefix = "" # 경고 메시지를 담을 변수
    # (A) 휴게시간 검증
    if current_field_id == "rest_time":
        rest_val = str(content.get("rest_time", "")).strip()
        negative_keywords = ["", "0", "0분", "없음", "없어요", "안해요", "없습니다", "아니요", "없어"]
        
        # 입력값이 없거나 부정적인 표현인 경우
        if rest_val in negative_keywords or rest_val == "None":
            start_t = content.get("start_time")
            end_t = content.get("end_time")
            
            if start_t and end_t:
                try:
                    total_hours = calculate_work_hours(start_t, end_t)
                    if total_hours >= 4:
                        # ⚠️ 경고 메시지 작성
                        warning_prefix = (
                            f"하루 근로시간이 총 {total_hours}시간입니다.\n"
                            f"근로시간이 4시간일 경우 30분 이상, 8시간일 경우 1시간 이상의 휴게시간을 근로시간 도중에 부여해야 합니다.\n\n"
                        )
                except:
                    pass

    # (B) 최저시급 검증
    if current_field_id == "salary_amount":
        try:
            raw_salary = content.get("salary_amount", "0")
            # 쉼표, 원, 공백 제거
            salary_str = str(raw_salary).replace(",", "").replace("원", "").strip()
            
            if salary_str.isdigit():
                hourly_wage = int(salary_str)
                MINIMUM_WAGE_2025 = 10030
                
                if 0 < hourly_wage < MINIMUM_WAGE_2025:
                    # ⚠️ 경고 메시지 작성
                    warning_prefix = (
                        f"입력하신 금액({hourly_wage:,}원)은 2025년 최저시급({MINIMUM_WAGE_2025:,}원)보다 낮습니다.\n"
                        f"최저임금법 위반 소지가 있으니 다시 확인 부탁드립니다.\n\n"
                    )
        except:
            pass
            
    # -----------------------------------------------------------
    # ✅ [3] 최종 메시지 조합 (경고 + 다음질문)
    # -----------------------------------------------------------
    # 만약 경고가 있으면 "경고 메시지 + (줄바꿈) + 원래 하려던 질문" 형태로 합칩니다.
    if warning_prefix:
        final_reply = warning_prefix + final_reply

    # -----------------------------------------------------------
    # ✅ [4] 채팅 기록 저장 및 반환
    # -----------------------------------------------------------
    
    # 봇의 최종 답변(경고 포함)을 히스토리에 저장
    new_chat_history.append({"sender": "bot", "message": final_reply})
    
    updated_value = new_fields.get(updated_key, "")

    if next_item:
        return schemas.ChatResponse(
            reply=final_reply,
            updated_field=updated_field_list, # ⭐️ 미리 만든 안전한 리스트 사용
            is_finished=False,
            full_contract_data=content,
            chat_history=new_chat_history 
        )

    else:
        return schemas.ChatResponse(
            reply="모든 항목이 작성되었습니다.",
            updated_field=updated_field_list, # ⭐️ 미리 만든 안전한 리스트 사용
            is_finished=True,
            full_contract_data=content,
            chat_history=new_chat_history 
        )


# -----------------------------------------------------------
# ✅ 5. DOCX 렌더링
# -----------------------------------------------------------
TEMPLATE_FILE = "working.docx"

async def render_docx(contract):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(current_dir, "..", "..", "templates", TEMPLATE_FILE)
    
    # 경로 디버깅용 (서버 콘솔에 실제 경로 출력)
    print(f"📂 Using template path: {template_path}")

    # 파일 존재 여부 검증
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"❌ Template not found at {template_path}")

    doc = DocxTemplate(template_path)
    context = contract.content or {}
    doc.render(context)
    return doc
