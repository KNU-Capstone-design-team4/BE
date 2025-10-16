import os
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from docx import Document
from docxtpl import DocxTemplate

from . import crud, models, schemas

# .env에 추가한 API키를 사용하도록 설정
client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


# 계약서 종류별로 필요한 필드와 질문 순서를 정의합니다.
# 프론트엔드와 이 field_id를 기준으로 화면을 업데이트하기로 약속해야 합니다.
#######계약서의 체크표시 해주는 코드는 아직 구성하지 않았음(2025.10.16)
CONTRACT_SCENARIOS = {
    "근로계약서":[
        # 1. 당사자 정보 (근로계약의 주체)
        {"field_id": "employer_name", "question": "먼저, 계약을 체결하는 고용주(대표자)의 성함은 무엇인가요? (예: 김철수)"},
        {"field_id": "business_name", "question": "고용주가 운영하는 사업체명(회사 이름)을 알려주세요. (예: (주)한빛유통)"},
        {"field_id": "business_phone", "question": "사업체의 대표 연락처(전화번호)를 입력해주세요. (예: 02-1234-5678)"},
        {"field_id": "business_address", "question": "사업장의 소재지(주소)는 어디인가요? (예: 서울시 강남구 테헤란로 123)"},
        {"field_id": "employee_name", "question": "이제 근로자(본인)의 성함은 무엇인가요? (예: 이영희)"},
        {"field_id": "employee_address", "question": "근로자의 현 주소는 어디인가요? (예: 경기도 성남시 분당구 정자일로 123)"},
        {"field_id": "employee_phone", "question": "근로자의 연락처(전화번호)를 입력해주세요. (예: 010-9876-5432)"},

        # 2. 계약 기간 및 장소 (날짜 정보)
        {"field_id": "contract_date", "question": "이 근로계약서를 최종적으로 작성한 날짜(계약일)는 언제인가요? (예: 2025년 10월 16일)"},
        {"field_id": "start_year", "question": "실제 근로를 시작하는 날(근로개시일)의 '년도'를 숫자로 알려주세요. (예: 2025)"},
        {"field_id": "start_month", "question": "실제 근로를 시작하는 날(근로개시일)의 '월'을 숫자로 알려주세요. (예: 1)"},
        {"field_id": "start_date", "question": "실제 근로를 시작하는 날(근로개시일)의 '일'을 숫자로 알려주세요. (예: 1)"},
        {"field_id": "work_location", "question": "근무하게 될 실제 장소(근무장소)를 알려주세요. (예: 사업장과 동일)"},
        {"field_id": "job_description", "question": "근로자가 수행할 업무 내용(직종)은 무엇인가요? (예: 사무 보조 및 서류 정리)"},

        # 3. 근로시간 및 휴일
        {"field_id": "work_day_count", "question": "일주일에 '총 몇 일'을 근무하나요? (숫자만 입력, 예: 5)"},
        {"field_id": "work_day_description", "question": "실제 근무 요일을 명시해주세요. (예: 월요일부터 금요일까지)"},
        {"field_id": "start_time", "question": "하루 근로를 시작하는 시간(시작 시간)을 알려주세요. (예: 09:00)"},
        {"field_id": "end_time", "question": "하루 근로를 마치는 시간(종료 시간)을 알려주세요. (예: 18:00)"},
        {"field_id": "rest_time", "question": "하루 중 주어지는 휴게시간은 총 몇 분인가요? (숫자만 입력, 예: 60)"},
        {"field_id": "is_eligible_for_weekly_holiday", "question": "주 15시간 이상 근무하여 법적으로 주휴수당 지급 대상에 해당하나요? (예: 네/아니오)"},
        {"field_id": "Weekly_Paid_Holiday", "question": "주휴일(유급휴일)로 지정된 요일은 무엇인가요? (지급 대상이 아닐 경우 'X'를 기재)"},

        # 4. 임금 (급여)
        {"field_id": "salary_payment_cycle", "question": "임금의 계산 단위는 월급, 일급, 시급 중 무엇인가요? (예: 월급)"},
        {"field_id": "salary_amount", "question": "월(일, 시간) 지급되는 총 임금액을 숫자로만 알려주세요. (예: 2500000)"},
        {"field_id": "is_bonus_paid", "question": "별도로 정기적인 상여금이 지급되나요? (예: 있음/없음)"},
        {"field_id": "bonus_amount", "question": "상여금이 있다면 그 금액은 얼마인가요? (없다면 '0' 기재)"},
        {"field_id": "is_allowance_paid", "question": "상여금 외 기타 급여(제수당 등)가 지급되나요? (예: 있음/없음)"},
        {"field_id": "allowance_details", "question": "기타 급여가 있다면 종류와 금액을 상세히 알려주세요. (예: 식대 10만원, 교통비 5만원 / 없다면 '없음' 기재)"},
        {"field_id": "salary_payment_date", "question": "임금은 매월 며칠에 지급되나요? (숫자만 입력, 예: 25)"},
        {"field_id": "payment_method_type", "question": "임금 지급 방법은 '계좌이체'인가요, '직접 현금 지급'인가요?"},

        # 5. 사회보험 및 기타
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

'''CONTRACT_TIPS = {
    # 팁 1: 근로계약 기간이 1년 미만일 때의 팁
    "SHORT_TERM_CONTRACT": {
        "condition_field": "end_date",
        "condition_check": lambda content, field: content.get(field, '기간 없음') != '기간 없음', 
        "tip_message": "💡 [꿀팁: 기간제 근로] 근로 종료일이 지정되었습니다. 계약 기간이 1년 미만인 경우, 해고 시점과 해고 사유를 명확히 해야 나중에 분쟁을 줄일 수 있습니다."
    },
    # 팁 2: 급여가 최저임금 기준보다 낮을 위험이 있을 때의 팁
    "LOW_SALARY_RISK": {
        "condition_field": "salary_amount",
        "condition_check": lambda content, field: (
            content.get(field) and 
            isinstance(content.get(field), str) and # 값이 문자열인지 확인
            int(content.get(field, '0').replace('원', '').replace(',', '').strip() or 0) < 2100000 
            # 210만원은 가상의 최저 월급 기준선. 실제 값은 연도별 최저임금 기준으로 계산해야 합니다.
        ),
        "tip_message": "⚠️ [중요: 최저임금] 입력하신 월 급여가 낮을 위험이 있습니다. 반드시 시급으로 환산하여 현재 최저시급(10,030원) 이상인지 확인하세요."
    }
}'''

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

            response = await client.chat.completions.create(
                model="gpt-4o",  # 또는 "gpt-3.5-turbo"
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0, # 일관된 답변을 위해 0으로 설정
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
            # API 호출 실패 시, 임시로 사용자 메시지 전체를 사용하고 에러 로그를 남깁니다.
            print(f"OpenAI API call failed: {e}")
            extracted_value = user_message
        
        # --- 핵심 수정 부분 끝 ---
        
        # 4. DB의 계약서 내용을 업데이트합니다.
        contract = await crud.update_contract_content(db, contract, current_question_item["field_id"], extracted_value)
        updated_field_info = schemas.UpdatedField(field_id=current_question_item["field_id"], value=extracted_value)

    # 5. DB 업데이트 후의 최신 계약서 내용을 다시 가져옵니다. (crud 함수가 업데이트된 객체를 반환하도록 수정했다면 이 부분은 필요 없습니다)
    final_content = contract.content or {}

    '''# 🟢 [수정] 팁 검사 및 상태 추적 로직 추가
    tip_to_display = ""
    tips_to_save = []
    
    # 이미 표시된 팁 목록을 DB 내용에서 가져옵니다. (없으면 빈 리스트)
    displayed_tips = final_content.get("_displayed_tips", []) 
    
    # 현재까지 저장된 모든 팁을 순회하며 조건을 검사합니다.
    for tip_key, tip_data in CONTRACT_TIPS.items():
        
        # 🟢 [추가] 이미 표시된 팁은 건너뛰고 다음 팁을 검사합니다.
        if tip_key in displayed_tips:
            continue
            
        field_id = tip_data["condition_field"]
        
        # 해당 필드가 답변되었고, 조건 검사 함수를 만족하는지 확인합니다.
        if field_id in final_content and tip_data["condition_check"](final_content, field_id):
            tip_to_display = tip_data["tip_message"]
            tips_to_save.append(tip_key) # 새로 표시되었으므로 저장 목록에 추가
            break # 첫 번째 조건을 만족하는 팁만 제공하고 종료

    # 🟢 [추가] 만약 팁이 표시되었다면, 해당 팁을 DB에 "표시됨"으로 저장하여 다음 턴에는 나오지 않게 합니다.
    if tips_to_save:
        updated_displayed_tips = displayed_tips + tips_to_save
        # contract.content의 '_displayed_tips' 필드만 업데이트합니다.
        contract = await crud.update_contract_content(db, contract, "_displayed_tips", updated_displayed_tips)
        # 최종 응답에 사용할 final_content도 업데이트합니다.
        final_content["_displayed_tips"] = updated_displayed_tips'''



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
        
    '''# 🟢 [추가] 팁 메시지를 다음 질문 앞에 추가합니다.
    if tip_to_display:
        reply_message = f"{tip_to_display}\n\n{reply_message}"'''

    # 7. 최종 응답을 프론트엔드에 보낼 형태로 구성합니다.
    return schemas.ChatResponse(
        reply=reply_message,
        updated_field=updated_field_info,
        is_finished=is_finished,
        full_contract_data=final_content
    ) 




'''def create_docx_from_contract(contract: models.Contract):
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
        
    return document'''

def create_docx_from_contract(contract: models.Contract):
    """
    DB에 저장된 계약서 정보로 .docx (워드) 문서를 생성합니다.
    """
    
    # 1. 템플릿 경로 설정 (프로젝트 루트의 templates 폴더 기준)
    # 현재 서비스 파일이 app 폴더 안에 있다면, 상위 폴더(BE)로 가서 templates를 찾습니다.
    # 이 경로는 실행 환경에 따라 정확히 맞춰주셔야 합니다!
    current_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(current_dir, "..", "templates", "working.docx")
    print(f"DEBUG: 시도 경로: {template_path}")
    
    # docxtpl 객체 생성 및 템플릿 로드
    try:
        doc = DocxTemplate(template_path)
    except FileNotFoundError:
        # 파일이 없으면 에러를 발생시키거나 빈 문서를 반환하는 등 적절히 처리해야 합니다.
        raise FileNotFoundError(f"템플릿 파일을 찾을 수 없습니다: {template_path}. 경로를 확인해주세요.")

    # 2. DB의 JSON 데이터를 렌더링 Context로 사용
    context = contract.content or {} 
    
    # 3. 템플릿에 데이터 채우기 (렌더링)
    doc.render(context)
    
    # 완성된 docxtpl 객체를 반환합니다.
    return doc 