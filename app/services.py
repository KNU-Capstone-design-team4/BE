import os
from sqlalchemy.ext.asyncio import AsyncSession
from docxtpl import DocxTemplate
from . import crud, models, schemas
from .ai_handlers import working_ai, foreign_ai, house_ai, attorney_ai

def find_next_question(contract):
    """contract_type 에 따라 적절한 AI 핸들러로 라우팅하고,
    return 값은 오직 '질문 문자열'만 반환한다."""

    content = contract.content or {}

    if contract.contract_type == "근로계약서":
        item, _ = working_ai.find_next_question(content)

    elif contract.contract_type == "통합신청서":
        item, _ = foreign_ai.find_next_question(content)
    
    elif contract.contract_type == "임대차계약서":
        item, _ = house_ai.find_next_question(content)     

    elif contract.contract_type == "위임장":
        item, _ = attorney_ai.find_next_question(content)

    # ✅ item이 None이면 다음 질문이 없다는 뜻 → None 반환
    if item is None:
        return None

    # ✅ item은 dict 형태 → 문자열(question)만 반환
    return item["question"]



def get_contract_handler(contract_type: str):
    """문서 종류에 맞는 핸들러 반환"""
    if contract_type == "근로계약서":
        return working_ai
    elif contract_type == "통합신청서":
        return foreign_ai
    elif contract_type == "위임장":
        return attorney_ai
    elif contract_type == "임대차계약서":
        return house_ai
    else:
        raise ValueError(f"지원하지 않는 계약서 타입입니다: {contract_type}")


# ---------------------------------------------------------
# ✅ 모든 문서 작성/질의 로직은 핸들러가 수행
# ---------------------------------------------------------
async def process_chat_message(
    db: AsyncSession,
    contract: models.Contract,
    user_message: str
) -> schemas.ChatResponse:
    """
    Dispatcher 역할만 수행한다.
    1) 핸들러 선택
    2) 핸들러에게 메시지를 위임
    3) 핸들러가 반환한 계약 데이터(content) DB 저장
    """

    try:
        handler = get_contract_handler(contract.contract_type)
    except ValueError as e:
        return schemas.ChatResponse(
            reply=str(e),
            updated_field=None,
            is_finished=True,
            full_contract_data={}
        )

    # ✅ 1) 핸들러가 메시지 전체 로직을 처리한다
    response: schemas.ChatResponse = await handler.process_message(
        db=db,
        contract=contract,
        message=user_message
    )

    # ✅ 2) 핸들러가 반환한 최신 content로 DB 업데이트
    if response.full_contract_data is not None:
        await crud.update_contract(
            db=db,
            contract_id=contract.id,
            new_content=response.full_contract_data,
            new_chat_history=response.chat_history
        )

    return response

'''async def process_chat_message(db, contract, message):

    if contract.contract_type == "근로계약서":
        handler = working_ai
    elif contract.contract_type == "통합신청서":
        handler = foreign_ai
    else:
        raise ValueError("Unknown contract type")

    return await handler.process_message(db, contract, message)
'''

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
