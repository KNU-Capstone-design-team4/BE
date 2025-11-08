import os
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from docx import Document
from docxtpl import DocxTemplate
import numpy as np
import json
import datetime
import asyncio  # 1. (추가) RAG용
import numpy as np  # 2. (추가) RAG용
from dotenv import load_dotenv  # 3. (추가) RAG용
from typing import List, Dict, Optional # 4. (추가) 타입 힌트

from . import crud, models, schemas
from .ai_handlers import working_ai
# from .ai_handlers import lease_ai # (나중에 추가)

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

def get_contract_handler(contract_type: str):
    """
    계약서 종류에 맞는 "전문가 핸들러" 모듈을 반환합니다.
    """
    if contract_type == "근로계약서":
        return working_ai
    
    # (나중에 '임대차계약서' 추가 시)
    # elif contract_type == "임대차계약서":
    #    return lease_ai
    
    else:
        # 지원하지 않는 계약서 타입일 경우 예외 발생
        raise ValueError(f"지원하지 않는 계약서 타입입니다: {contract_type}")
    
'''async def process_chat_message(db: AsyncSession, contract: models.Contract, user_message: str):
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
    ) '''

async def process_chat_message(db: AsyncSession, contract: models.Contract, user_message: str) -> schemas.ChatResponse:
    """
    [하이브리드 챗봇 - 교통정리(Dispatcher)]
    1. 계약서 종류에 맞는 '전문가 핸들러'를 선택합니다.
    2. '시작/RAG/폼'을 판별합니다.
    3. '폼'일 경우, '전문가 핸들러'에게 AI 처리를 위임합니다.
    """
    
    try:
        # 1. 계약서 종류에 맞는 "전문가"를 불러옵니다.
        handler = get_contract_handler(contract.contract_type)
    except ValueError as e:
        # 지원하지 않는 계약서 타입일 경우 (예: "임대차계약서" 핸들러가 아직 없음)
        return schemas.ChatResponse(
            reply=str(e), updated_field=None, is_finished=True, full_contract_data={}
        )

    # --- 2. 현재 폼 작성 상태 파악 (전문가에게 위임) ---
    current_content = contract.content or {}
    
    # '전문가'에게 현재 content를 기반으로 다음 질문을 찾아달라고 요청
    current_question_item, current_question_index = handler.find_next_question(current_content)

    # --- 3. "시작/재개 신호" 처리 ---
    if user_message.strip() == "" or user_message.strip() == "string":
        reply_message: str
        is_finished: bool
        
        if current_question_item:
            reply_message = current_question_item['question']
            is_finished = False
        else:
            reply_message = "모든 항목이 작성되었습니다. 계약서 다운로드를 진행하시거나, 법률 관련 팁이 궁금하시면 질문해주세요."
            is_finished = True
        
        return schemas.ChatResponse(
            reply=reply_message, updated_field=None, is_finished=is_finished, full_contract_data=current_content
        )

    # --- 4. 입력 분류: 법률 질문(RAG)인지 폼 답변인지 판별 ---
    relevant_tips, top_score = await find_top_relevant_tips(user_message)
    is_legal_question = top_score >= SIMILARITY_THRESHOLD

    # --- 5. 로직 분기 ---

    if is_legal_question:
        # --- [분기 A] 법률 질문(RAG) ---
        rag_answer = await get_rag_response(user_message, relevant_tips)
        
        if current_question_item:
            re_ask_prompt = f"\n\n[이어서 진행]\n{current_question_item['question']}"
            is_finished = False
        else:
            re_ask_prompt = "\n\n(계약서 작성은 완료된 상태입니다. 추가로 궁금한 점이 있으신가요?)"
            is_finished = True
            
        final_reply = rag_answer + re_ask_prompt

        return schemas.ChatResponse(
            reply=final_reply, updated_field=None, is_finished=is_finished, full_contract_data=current_content
        )

    else:
        # --- [분기 B] 폼 답변 ---

        if not current_question_item:
            reply = "모든 항목이 작성되었습니다. 계약서 다운로드를 진행하시거나, 법률 관련 팁이 궁금하시면 질문해주세요."
            return schemas.ChatResponse(
                reply=reply, updated_field=None, is_finished=True, full_contract_data=current_content
            )

        # 5-B-1. '전문가 핸들러'에게 AI 추출을 위임
        ai_json_response = await handler.get_smart_extraction(
            client,
            current_question_item["field_id"], 
            user_message, 
            current_question_item['question']
        )
        
        status = ai_json_response.get("status")
        filled_fields = ai_json_response.get("filled_fields", {})
        skip_n = ai_json_response.get("skip_next_n_questions", 0)
        follow_up = ai_json_response.get("follow_up_question")

        # 5-B-2. AI JSON 응답에 따라 분기
        
        if status == "clarify":
            # [되묻기] AI가 정보가 부족하여 되물어봄
            return schemas.ChatResponse(
                reply=follow_up, 
                updated_field=None,
                is_finished=False,
                full_contract_data=current_content 
            )
        
        if status == "success":
            # [성공] DB 저장 (crud.py의 새 함수 호출)
            contract = await crud.update_contract_content_multiple(db, contract, filled_fields)
            
            updated_field_info = None
            if filled_fields:
                first_key = next(iter(filled_fields))
                updated_field_info = schemas.UpdatedField(field_id=first_key, value=filled_fields[first_key])
            
            new_content = contract.content or {} 

            # 5-B-3. 다음 질문 찾기 (스킵 로직 포함)
            # (⭐️ 수정) 현재 시나리오와 인덱스를 '전문가'로부터 다시 받아와야 함
            scenario = handler.CONTRACT_SCENARIO_LABOR # (임시. 추후엔 handler.get_scenario() 호출)
            
            next_question_index = current_question_index + 1 + skip_n
            
            if next_question_index < len(scenario):
                next_question_item = scenario[next_question_index]
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
        
        # (예외 처리)
        reply = f"죄송합니다. 답변을 이해하지 못했습니다.\n\n[이어서 진행]\n{current_question_item['question']}"
        return schemas.ChatResponse(
            reply=reply, updated_field=None, is_finished=False, full_contract_data=current_content
        )

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