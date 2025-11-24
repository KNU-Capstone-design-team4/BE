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

import httpx
import xml.etree.ElementTree as ET

##행정안전부 ##배포하면 다시 발급받아야함
REAL_JUSO_API_KEY = os.environ.get("JUSO_API_KEY", "devU01TX0FVVEgyMDI1MTEyNDAxMTcyOTExNjQ4NDk=")
##국토교통부
BUILDING_API_KEY = os.environ.get("BUILDING_API_KEY", "283c37c89ec3aac9cd025a29d0b73c7d075be291b3ebe3b1b26de62794719038")
BUILDING_API_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"

from app import schemas

client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

CONTRACT_SCENARIO=[
    {
        "field_id": "property_description_text", 
        "question": "등기 신청을 할 부동산의 정확한 주소를 알려주세요. (예: 서울시 서초구 서초동 100, 서초아파트 101동 505호)"
    },
    # --- 2. 등기 원인 및 목적 ---
    {
        "field_id": "reg_cause_type", 
        "question": "등기의 원인은 무엇인가요? (예: 매매, 증여, 상속, 근저당권설정)"
    },
    {
        "field_id": "reg_cause_date", 
        "question": "등기 원인이 발생한 날짜(계약일 또는 잔금일)는 언제인가요? (예: 2025년 3월 4일)"
    },
    {
        "field_id": "reg_purpose", 
        "question": "등기의 목적은 무엇인가요? (예: 소유권이전, 근저당권설정)"
    },
    {
        "field_id": "transfer_share", 
        "question": "부동산을 전부 이전하시나요, 아니면 일부(지분)만 이전하시나요? (예: 소유권 전부, 2분의 1)"
    },
    # --- 3. 위임인 정보 (등기의무자 - 파는 사람 / 매도인) ---
    {
        "field_id": "delegator_1_name", 
        "question": "등기의무자(매도인 - 파는 분)의 성함은 무엇인가요?"
    },
    {
        "field_id": "delegator_1_address", 
        "question": "등기의무자의 주민등록상 주소를 상세히 알려주세요."
    },
    # --- 4. 위임인 정보 ---
    {
        "field_id": "delegator_2_name", 
        "question": "등기권리자(매수인 - 사는 분)의 성함은 무엇인가요?"
    },
    {
        "field_id": "delegator_2_address", 
        "question": "등기권리자의 주민등록상 주소를 상세히 알려주세요."
    },
    # --- 5. 대리인 정보 (법무사 등) ---
    {
        "field_id": "agent_name", 
        "question": "위임을 받는 대리인(법무사 등)의 성함은 무엇인가요?"
    },
    {
        "field_id": "agent_address", 
        "question": "대리인의 사무실 주소(소재지)를 알려주세요."
    },
    # --- 6. 위임 일자 ---
    {
        "field_id": "delegation_date", 
        "question": "위임장에 기재할 위임 일자는 언제인가요? (예: 2025년 3월 4일)"
    }
]

TIP_LIST = [
    "1. (신청서와 내용 일치) 위임장의 ①부동산의 표시, ②등기원인과 연월일, ③등기의 목적, ④공란 등은 등기신청서 기재요령에 따라 기재해야 하며, 등기신청서의 해당 부분 내용과 완전히 동일하게 적어야 합니다.",
    "2. (대리인 인적사항) ⑤대리인 란에는 위임을 받는 사람, 즉 등기소에 제출하러 가는 사람의 성명과 주소를 기재합니다.",
    "3. (위임 날짜 기재) 실제로 등기 신청 권한을 위임한 날짜를 기재합니다.",
    "4. (위임인 작성법) ⑦위임인 란에는 등기신청인의 성명과 주소를 기재하고 날인해야 합니다.",
    "5. (인감 날인 필수 조건) 등기의무자의 인감증명서를 첨부해야 하는 등기인 경우에는 위임인 란에 막도장이 아닌 반드시 그의 인감을 날인해야 합니다.",
    "6. (법인 및 단체 기재사항) 신청인이 법인이거나 법인 아닌 사단·재단인 경우, 상호(명칭)와 본점(주사무소 소재지), 그리고 대표자(관리인)의 성명과 주소를 모두 기재해야 합니다.",
    "7. (법인 인감 날인) 법인이 인감증명을 첨부해야 할 때는 등기소의 증명을 얻은 그 대표자의 인감(법인인감)을 날인합니다.",
    "8. (비법인 단체 날인) 법인 아닌 사단이나 재단인 경우에는 대표자(관리인)의 개인인감을 날인해야 합니다.",
    "9. (일반인 대리 제한) 변호사나 법무사가 아닌 일반인은 보수와 관계없이 대리인으로서 반복하여 계속적으로 등기신청을 할 수 없습니다.",
    "10. (가족관계 등 소명) 신청인이 업(業, 계속·반복적)으로 한다는 의심이 있는 경우, 등기관은 대리인에게 본인과의 관계를 가족관계증명서나 주민등록등본 등으로 소명할 것을 요청할 수 있습니다."
]

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
        system_prompt = f"""
        당신은 부동산 등기 전문가입니다.
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

async def get_building_info(sigungu_cd, bjdong_cd, bun, ji):
    params = {
        "serviceKey": BUILDING_API_KEY,
        "sigunguCd": sigungu_cd,
        "bjdongCd": bjdong_cd,
        "bun": bun.zfill(4),
        "ji": ji.zfill(4),
        "numOfRows": 1,
        "_type": "json"
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(BUILDING_API_URL, params=params, timeout=5.0)
            if response.status_code != 200: return None
            
            # JSON 파싱
            try: data = response.json()
            except: return None

            items = data.get("response", {}).get("body", {}).get("items", {}).get("item")
            if isinstance(items, list) and items: return items[0]
            elif isinstance(items, dict): return items
            return None
    except Exception as e:
        print(f"건축물대장 조회 실패: {e}")
        return None


# (메인 함수) 주소로 텍스트 생성
async def get_property_text_by_address(address_query: str) -> str:
    print(f"🔍 [API 조회] 검색어: {address_query}")
    
    # 1. 도로명주소 API 호출
    url = "https://business.juso.go.kr/addrlink/addrLinkApi.do"
    params = {
        "confmKey": REAL_JUSO_API_KEY,
        "currentPage": 1,
        "countPerPage": 1,
        "keyword": address_query,
        "resultType": "json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            data = response.json()
            
            juso_list = data.get("results", {}).get("juso", [])
            if not juso_list:
                return f"'{address_query}' 주소를 찾을 수 없습니다. 정확한 주소를 입력해 주세요."
            
            # 2. 주소 정보 추출
            item = juso_list[0]
            road_addr = item.get("roadAddr", "")
            jibun_addr = item.get("jibunAddr", "")
            bd_nm = item.get("bdNm", "")
            
            # 행정구역 코드 파싱
            adm_cd = item.get("admCd", "")
            lnbr_mnnm = item.get("lnbrMnnm", "")
            lnbr_slno = item.get("lnbrSlno", "")
            
            sigungu_cd = adm_cd[:5]
            bjdong_cd = adm_cd[5:]
            
            # 3. 건축물대장 API 호출 (연결)
            bld_info = await get_building_info(sigungu_cd, bjdong_cd, lnbr_mnnm, lnbr_slno)
            
            # 4. 텍스트 조립
            area = "00.0"
            structure = "구조미상"
            main_use = "용도미상"
            
            if bld_info:
                area = bld_info.get("platArea") or bld_info.get("totArea") or "00.0"
                structure = bld_info.get("strctCdNm") or "구조미상"
                main_use = bld_info.get("mainPurpsCdNm") or "용도미상"
                
            result_text = f"1. {jibun_addr}\n"
            result_text += f"   대 {area}㎡\n"
            result_text += f"2. {jibun_addr}\n"
            result_text += f"   [도로명주소] {road_addr}\n"
            
            if bd_nm:
                result_text += f"   {bd_nm}\n"
            
            result_text += f"   {structure} {main_use}\n"
            result_text += "   (상세 내용은 등기부등본 참조)\n"
            result_text += "이          상"
            
            return result_text

    except Exception as e:
        print(f"❌ API 오류: {e}")
        return f"오류 발생: {address_query}"
    
    # --- [AI] 스마트 추출기 ---
async def get_smart_extraction(client: AsyncOpenAI, field_id: str, user_message: str, question: str) -> Dict:
        today = datetime.date.today()
        current_year = today.year
        json_format_example = '{"status": "success", "filled_fields": {"key": "value"}, "skip_next_n_questions": 0, "follow_up_question": null}'
        
        # 부동산 위임장 전용 프롬프트
        system_prompt = f"""
        당신은 사용자의 답변에서 부동산 등기 위임장 작성에 필요한 핵심 정보를 추출하는 AI입니다.
        오늘은 {today.strftime('%Y년 %m월 %d일')}입니다.(현재 연도는 {current_year}년)

        [규칙]
        1. 사용자의 답변이 충분하면 'success', 부족하면 'clarify'와 되묻는 질문을 생성하세요.
        2. 반환하는 JSON의 키(Key)는 반드시 제공된 "{field_id}"와 글자 하나 틀리지 않고 똑같아야 합니다. 절대 키 이름을 번역하거나 임의로 변경하지 마십시오. (예: 'reg_cause' -> '등기원인'으로 바꾸지 말 것)
        3. 날짜는 'YYYY년 MM월 DD일', 지분은 '소유권 전부' 또는 '2분의 1'과 같이 한글로 추출하세요.
        4. 답변에 추가적인 설명이 있어도 핵심 값만 추출하세요.
        5. 성명(이름)을 묻는 질문에는 사용자가 '홍길', '이 산' 처럼 2글자나 외자 이름을 입력하더라도, 오타가 명확하지 않다면 그대로 추출하세요. 되묻지 마십시오.

        
        [예시]
        Q: 등기 원인일은 언제인가요?
        A: 작년 12월 25일이요.
        -> filled_fields: {{"{field_id}": "{current_year - 1}년 12월 25일"}}
        
        Q: 지분은 어떻게 되나요?
        A: 반반입니다.
        -> filled_fields: {{"{field_id}": "2분의 1"}}

        Q: 매도인 성함이요?
        A: 홍길동입니다.
        -> filled_fields: {{"{field_id}": "홍길동"}}
        
        [JSON 포맷]
        {json_format_example}
        """
        
        try:
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Question: \"{question}\"\nUser Answer: \"{user_message}\""}
                ],
                temperature=0,
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"AI Extraction Error: {e}")
            return {"status": "success", "filled_fields": {field_id: user_message}, "skip_next_n_questions": 0}

    # --- [보조] 다음 질문 찾기 ---
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
    if current_bot_question:
        new_chat_history.append({"sender": "bot", "message": current_bot_question})
    
    new_chat_history.append({"sender": "user", "message": message})


    ##주소##
    if current_item and current_item["field_id"] == "property_description_text":
         
         # 1. 임시 저장된 주소 정보 확인
         temp_text = content.get("temp_property_text")

         # [공통 변수 선언]
         positive_answers = ["네", "예", "맞아요", "맞습니다", "응", "ㅇㅇ", "yes", "ok"]
         negative_answers = ["아니요", "아니", "ㄴㄴ", "no", "놉", "틀렸어", "틀립니다"]
         msg_clean = message.strip().replace(".", "").replace("!", "")

         # [Case A] 확인 대기 중 (이미 한 번 조회함)
         if temp_text:
             
             # (1) "네" -> 최종 확정 및 저장
             if any(ans == msg_clean or msg_clean.startswith(ans) for ans in positive_answers):
                 content["property_description_text"] = temp_text
                 content.pop("temp_property_text", None) # 임시 데이터 삭제
                 
                 next_item, _ = find_next_question(content)
                 
                 # 멘트 분리해서 저장
                 new_chat_history.append({"sender": "bot", "message": "네, 확인했습니다."})

                 if next_item:
                     next_question = next_item['question']
                     new_chat_history.append({"sender": "bot", "message": next_question})
                     reply = next_question
                 else:
                     reply = "모든 항목이 작성되었습니다."
                     new_chat_history.append({"sender": "bot", "message": reply})
                 
                 return schemas.ChatResponse(
                     reply="",
                     updated_field=[{"field_id": "property_description_text", "value": temp_text}],
                     is_finished=(next_item is None),
                     full_contract_data=content,
                     chat_history=new_chat_history
                 )
             
             # ⭐️ [핵심 수정 부분] (2) 부정 답변 키워드인 경우 -> 재입력 요청 (API 호출 X)
             elif any(word in msg_clean for word in negative_answers):
                 reply = "네, 알겠습니다. 수정할 주소를 다시 입력해 주세요."
                 new_chat_history.append({"sender": "bot", "message": reply})
                 
                 return schemas.ChatResponse(
                     reply=reply,
                     updated_field=None, 
                     is_finished=False,
                     full_contract_data=content,
                     chat_history=new_chat_history
                 )
             
             # (3) 새로운 주소로 간주 -> 재조회 (API 호출)
             else:
                 full_text = await get_property_text_by_address(message)
                 content["temp_property_text"] = full_text # 임시 데이터 갱신
                 
                 reply = f"주소를 다시 조회했습니다.\n\n[조회 결과]\n{full_text}\n\n이 정보가 맞나요?"
                 new_chat_history.append({"sender": "bot", "message": reply})
                 
                 return schemas.ChatResponse(
                     reply=reply,
                     updated_field=None, 
                     is_finished=False,
                     full_contract_data=content,
                     chat_history=new_chat_history
                 )

         # [Case B] 처음 주소를 입력하는 경우 (if temp_text: 에 대한 else)
         else:
             full_text = await get_property_text_by_address(message)
             content["temp_property_text"] = full_text
             
             reply = f"주소를 확인하여 부동산 정보를 불러왔습니다.\n\n[조회 결과]\n{full_text}\n\n정보가 맞다면 '네', 아니라면 정확한 주소를 다시 입력해주세요."
             
             new_chat_history.append({"sender": "bot", "message": reply})
             
             return schemas.ChatResponse(
                 reply=reply,
                 updated_field=None,
                 is_finished=False,
                 full_contract_data=content,
                 chat_history=new_chat_history
             )
        ### 주소 ###
    
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
        

    # ✅ 다음 질문 찾기
    next_item, _ = find_next_question(content)

    # -----------------------------------------------------------------
    # ✅ [4. CHAT HISTORY 추가]
    # updated_key는 폼 답변 성공 시에만 정의되므로, 
    # 'if next_item:' 블록 밖으로 이동시키거나 안전하게 처리합니다.
    updated_key = list(new_fields.keys())[0] if new_fields else None
    # -----------------------------------------------------------------
    
    if next_item:
        return schemas.ChatResponse(
            reply=next_item["question"],
            updated_field=[{
                "field_id": updated_key,
                "value": new_fields[updated_key]
            }] if updated_key else [],            
            is_finished=False,
            full_contract_data=content,
            chat_history=new_chat_history # ⬅️ 추가
        )

    else:
        return schemas.ChatResponse(
            reply="모든 항목이 작성되었습니다.",
            updated_field=[{
                "field_id": updated_key,
                "value": new_fields[updated_key]
            }] if updated_key else None,
            is_finished=True,
            full_contract_data=content,
            chat_history=new_chat_history # ⬅️ 추가
        )



# -----------------------------------------------------------
# ✅ 4. DOCX 렌더링 함수 (템플릿 파일: working.docx)
# -----------------------------------------------------------

TEMPLATE_FILE = "attorney.docx"

async def render_docx(contract):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 경로 설정 (상위 templates 폴더 등 프로젝트 구조에 맞춰 수정)
    template_path = os.path.join(current_dir, "..", "..", "templates", TEMPLATE_FILE)
    
    print(f"📂 Using template path: {template_path}")

    if not os.path.exists(template_path):
        raise FileNotFoundError(f"❌ Template not found at {template_path}")

    doc = DocxTemplate(template_path)
    context = contract.content or {}
    doc.render(context)
    return doc