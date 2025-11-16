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
from typing import List, Dict, Optional,Any,Tuple# 4. (추가) 타입 힌트

from . import crud, models, schemas
from .ai_handlers import working_ai,foreign_ai

load_dotenv()
client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# ---------------------------------------------------------
# ✅ RAG 기능 중앙 집중화
# ---------------------------------------------------------

# RAG 임계값 (핸들러에서 가져와야 하지만, 중앙 관리를 위해 여기에 정의)
SIMILARITY_THRESHOLD = 0.4 

# 전역 변수로 임베딩과 잠금 관리
tip_embeddings: List[np.ndarray] = []
tip_embeddings_lock = asyncio.Lock()

# ⭐️ 모든 핸들러 모듈을 리스트로 정의
HANDLER_MODULES = [working_ai, foreign_ai]

def get_all_tips(handler_modules: List[Any]) -> List[str]:
    """모든 핸들러 모듈에서 TIP_LIST를 수집하여 통합합니다."""
    # RAG 임베딩 생성을 위해 모든 팁을 모읍니다.
    all_tips = []
    for handler in handler_modules:
        if hasattr(handler, 'TIP_LIST'):
            all_tips.extend(handler.TIP_LIST) 
    return all_tips

async def get_tip_embeddings(handler_modules: List[Any]) -> List[np.ndarray]:
    """팁 목록 임베딩을 (최초 1회) 생성하고 캐시합니다."""
    global tip_embeddings
    
    if tip_embeddings:
        return tip_embeddings
        
    all_tips = get_all_tips(handler_modules)
    
    async with tip_embeddings_lock:
        if not tip_embeddings:
            print(f"RAG 팁 목록 ({len(all_tips)}개) 임베딩을 생성합니다...")
            embeddings_response = await client.embeddings.create(
                model="text-embedding-3-small",
                input=all_tips
            )
            tip_embeddings = [np.array(data.embedding) for data in embeddings_response.data]
            print("RAG 임베딩 생성 완료!")
    return tip_embeddings

async def get_embedding(text: str) -> np.ndarray:
    """단일 텍스트의 임베딩을 반환합니다."""
    response = await client.embeddings.create(model="text-embedding-3-small", input=text)
    return np.array(response.data[0].embedding)


# ⭐️⭐️⭐️ 수정된 RAG 검색 함수: 현재 핸들러의 팁만 사용 ⭐️⭐️⭐️
async def find_top_relevant_tips(
    question: str, 
    handler_module: Any, # 현재 계약 타입 핸들러
    handler_modules_all: List[Any], # 전체 핸들러 리스트
    top_n=3
) -> Tuple[str, float]:
    
    # 1. 전체 임베딩과 전체 팁 목록 로드 (캐시 사용)
    all_embeddings = await get_tip_embeddings(handler_modules_all)
    all_tips = get_all_tips(handler_modules_all)
    
    # 2. 현재 핸들러의 팁 목록을 가져와서 전체 목록에서의 인덱스를 매핑합니다.
    target_tips = getattr(handler_module, 'TIP_LIST', [])
    if not target_tips:
        return "", 0.0

    target_indices = []
    # 중복 문제가 발생할 수 있지만, 여기서는 간단한 index() 방식을 사용합니다.
    for tip in target_tips:
        try:
            full_index = all_tips.index(tip) 
            target_indices.append(full_index)
        except ValueError:
            # 팁이 전체 리스트에 없다면 무시합니다. (발생해서는 안 됨)
            continue
            
    # 3. 필터링된 임베딩 서브셋 생성
    target_embeddings = [all_embeddings[i] for i in target_indices]
    
    question_embedding = await get_embedding(question)
    
    # 4. 서브셋 내에서 유사도 계산
    similarities = [np.dot(question_embedding, emb) for emb in target_embeddings]
    
    if not similarities:
        return "", 0.0
        
    # 5. 결과 추출
    top_relative_indices = np.argsort(similarities)[-top_n:][::-1]
    
    top_score = similarities[top_relative_indices[0]]
    relevant_tips_str = "\n\n".join([target_tips[i] for i in top_relative_indices])
    
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
    """
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": question}],
        temperature=0,
    )
    return response.choices[0].message.content.strip()


# ---------------------------------------------------------
# ✅ Dispatcher 및 핸들러 라우팅 함수
# ---------------------------------------------------------

def get_contract_handler(contract_type: str):
    """문서 종류에 맞는 핸들러 반환"""
    if contract_type == "근로계약서":
        return working_ai
    elif contract_type == "통합신청서":
        return foreign_ai
    else:
        raise ValueError(f"지원하지 않는 계약서 타입입니다: {contract_type}")

# ---------------------------------------------------------
# ✅ 메인 챗봇 처리 함수 (Dispatcher)
# ---------------------------------------------------------

async def process_chat_message(
    db: AsyncSession,
    contract: models.Contract,
    user_message: str
) -> schemas.ChatResponse:
    """
    [하이브리드 챗봇 - 교통정리(Dispatcher)]
    1. 핸들러 선택 및 RAG/폼 분기 처리.
    2. 폼 답변 처리는 핸들러에게 위임한다.
    """
    
    try:
        handler = get_contract_handler(contract.contract_type)
    except ValueError as e:
        return schemas.ChatResponse(
            reply=str(e), updated_field=None, is_finished=True, full_contract_data={}
        )

    # --- 2. 현재 폼 작성 상태 파악 ---
    content = contract.content or {}
    # '전문가'에게 현재 content를 기반으로 다음 질문을 찾아달라고 요청
    # ⚠️ working_ai.find_next_question은 (item, index)를 반환하도록 수정되어야 함
    current_question_item, current_question_index = handler.find_next_question(content)

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
            reply=reply_message, updated_field=None, is_finished=is_finished, full_contract_data=content
        )

    # --- 4. 입력 분류: 법률 질문(RAG)인지 폼 답변인지 판별 ---
    # ⭐️ 수정: 현재 핸들러의 팁만 사용하여 RAG 검색
    relevant_tips, top_score = await find_top_relevant_tips(user_message, handler, HANDLER_MODULES) 
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
            reply=final_reply, updated_field=None, is_finished=is_finished, full_contract_data=content
        )

    else:
        # --- [분기 B] 폼 답변 ---

        if not current_question_item:
            reply = "모든 항목이 작성되었습니다. 계약서 다운로드를 진행하시거나, 법률 관련 팁이 궁금하시면 질문해주세요."
            return schemas.ChatResponse(
                reply=reply, updated_field=None, is_finished=True, full_contract_data=content
            )

        # ⭐️ 폼 답변 처리는 핸들러에게 위임
        # handler.process_message는 내부적으로 DB 저장(crud) 및 다음 질문 찾기를 모두 처리합니다.
        # ⚠️ working_ai.get_smart_extraction 호출 시 handler를 사용
        ai = await handler.get_smart_extraction(
            current_question_item["field_id"],
            user_message,
            current_question_item["question"]
        )

        # 2. AI가 반환한 filled_fields 적용
        new_fields = ai.get("filled_fields", {})
        content.update(new_fields) # 👈 누적 데이터 병합

        # 3. skip_next_n_questions 적용
        skip_n = ai.get("skip_next_n_questions", 0)
        for _ in range(skip_n):
            next_item_to_skip, _ = handler.find_next_question(content)
            if next_item_to_skip:
                content[next_item_to_skip["field_id"]] = "__SKIPPED__"
            else:
                break
        
        # 4. DB 저장
        try:
            # crud는 services.py에서 이미 import 되어 있음
            contract = await crud.update_contract_content_multiple(db, contract, content)
            content = contract.content or {} # DB에서 최신 데이터(누적된 내용)를 다시 로드
        except Exception as e:
            # DB 저장 실패 로직은 working_ai에서 가져온 로직과 동일
            return schemas.ChatResponse(
                reply=f"데이터 저장 중 오류가 발생했습니다: {e}",
                updated_field=None,
                is_finished=False,
                full_contract_data=contract.content or {}
            )

        # 5. follow-up 질문이 있으면 그대로 반환
        if ai.get("status") == "clarify":
            return schemas.ChatResponse(
                reply=ai["follow_up_question"],
                updated_field=None,
                is_finished=False,
                full_contract_data=content
            )

        # 6. 다음 질문 찾기
        next_item, _ = handler.find_next_question(content)

        # 7. new_fields를 UpdatedField 리스트로 변환 (working_ai에서 가져온 헬퍼 함수)
        def make_updated_field_list(fields: Dict[str, Any]) -> Optional[List[schemas.UpdatedField]]:
            if not fields:
                return None
            lst: List[schemas.UpdatedField] = []
            for k, v in fields.items():
                lst.append(schemas.UpdatedField(field_id=k, value=v))
            return lst

        updated_field_list = make_updated_field_list(new_fields)

        # 8. 최종 응답 반환
        if next_item:
            return schemas.ChatResponse(
                reply=next_item["question"],
                updated_field=updated_field_list,
                is_finished=False,
                full_contract_data=content # 👈 누적된 데이터 포함
            )
        else:
            return schemas.ChatResponse(
                reply="모든 항목이 작성되었습니다.",
                updated_field=updated_field_list,
                is_finished=True,
                full_contract_data=content # 👈 누적된 데이터 포함
            )
# ---------------------------------------------------------
# ✅ 문서 생성도 핸들러에게 위임
# ---------------------------------------------------------
async def create_docx_from_contract(contract: models.Contract):
    """
    각 문서 타입의 핸들러가 template 파일을 알고 있고
    render_docx()에서 직접 .docx를 만들어 반환한다.
    """

    handler = get_contract_handler(contract.contract_type)

    # 핸들러에서 DocxTemplate 객체를 직접 생성해 반환해야 한다.
    doc: DocxTemplate = await handler.render_docx(contract)

    return doc
