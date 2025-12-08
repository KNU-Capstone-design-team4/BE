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
from urllib.parse import unquote

##행정안전부 ##배포하면 다시 발급받아야함
REAL_JUSO_API_KEY = os.environ.get("JUSO_API_KEY", "devU01TX0FVVEgyMDI1MTIwNDIwMzIwMTExNjUzNDc=")
#################devU01TX0FVVEgyMDI1MTEyNDAxMTcyOTExNjQ4NDk=###################

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
    "3. (위임 날짜 기재) 실제로 등기 신청 권한을 위임한 날짜를 기재합니다. 보통 잔금일이나 법무사에게 서류를 넘겨준 날짜를 적습니다.",
    "4. (위임인 작성법) ⑦위임인 란에는 등기신청인의 성명과 주소를 기재하고 날인해야 합니다.",
    "5. (인감 날인 필수 조건) 등기의무자(매도인, 증여자 등)의 인감증명서를 첨부해야 하는 등기인 경우에는 위임인 란에 막도장이 아닌 반드시 그의 '인감'을 날인해야 합니다.",
    "6. (법인 및 단체 기재사항) 신청인이 법인이거나 법인 아닌 사단·재단인 경우, 상호(명칭)와 본점(주사무소 소재지), 그리고 대표자(관리인)의 성명과 주소를 모두 기재해야 합니다.",
    "7. (법인 인감 날인) 법인이 인감증명을 첨부해야 할 때는 등기소의 증명을 얻은 그 대표자의 인감(법인인감)을 날인합니다.",
    "8. (비법인 단체 날인) 법인 아닌 사단이나 재단인 경우에는 대표자(관리인)의 개인인감을 날인해야 합니다.",
    "9. (일반인 대리 제한) 변호사나 법무사가 아닌 일반인은 보수와 관계없이 대리인으로서 반복하여 계속적으로 등기신청을 할 수 없습니다. (법무사법 위반)",
    "10. (가족관계 등 소명) 신청인이 업(業, 계속·반복적)으로 한다는 의심이 있는 경우, 등기관은 대리인에게 본인과의 관계를 가족관계증명서나 주민등록등본 등으로 소명할 것을 요청할 수 있습니다.",
    "11. (도로명 주소 사용) 부동산의 표시는 등기부등본을 따르지만, 사람(위임인, 대리인)의 주소는 반드시 '주민등록초본' 상의 최신 '도로명 주소'를 정확히 기재해야 합니다.",
    "12. (공동소유 지분 기재) 부동산이 공유(공동소유)인 경우, '공유자 지분 2분의 1 홍길동'과 같이 이전할 지분과 당사자를 명확히 적어야 합니다.",
    "13. (주소 변동 확인) 등기의무자(파는 사람)의 등기부상 주소와 현재 주민등록상 주소가 다른 경우, 주소변경등기를 선행하거나 이를 포함한 위임장 작성이 필요할 수 있습니다.",
    "14. (주민등록번호 기재) 위임인 및 대리인의 성명 옆이나 아래에 주민등록번호를 정확하게 기재하여 당사자 일치 여부를 명확히 합니다.",
    "15. (간인 처리) 위임장이 두 장 이상일 경우, 앞장 뒷면과 뒷장 앞면에 걸쳐 위임인의 인감으로 '간인(겹쳐 찍기)'을 해야 서류의 일체성이 증명됩니다.",
    "16. (정정인 날인) 위임장의 내용을 수정할 때는 수정테이프를 쓰지 말고, 두 줄을 긋고 수정한 뒤 그 옆에 위임인의 인감으로 '정정인'을 날인해야 효력이 있습니다.",
    "17. (인감증명서 유효기간) 첨부하는 인감증명서는 발행일로부터 3개월 이내의 것이어야 하며, 위임장에 찍힌 도장이 이 인감증명서와 일치하는지 육안으로 꼼꼼히 확인해야 합니다.",
    "18. (미성년자 대리) 위임인이 미성년자인 경우, 법정대리인(부모)이 위임장에 기재하고 부모의 인감을 날인한 뒤, 가족관계증명서 등을 첨부해야 합니다.",
    "19. (재외국민 위임) 재외국민(해외 거주 한국인)이 위임할 경우, 재외공관(영사관)에서 공증받은 위임장을 사용하거나, 인감도장을 날인하고 재외국민용 인감증명서를 첨부해야 합니다.",
    "20. (외국인 위임) 외국인은 서명인증서나 본국 관공서의 증명서를 첨부하며, 위임장에 서명 또는 날인합니다. 인감제도가 없는 국가의 경우 서명이 원칙입니다.",
    "21. (등기권리자 막도장) 등기권리자(매수인, 사는 사람)는 원칙적으로 인감증명서 첨부 의무가 없으므로, 위임장에 막도장을 찍거나 서명해도 무방한 경우가 많습니다.",
    "22. (매도용 인감증명서) 소유권이전등기(매매) 시 매도인은 반드시 '부동산 매도용 인감증명서'를 발급받아 제출해야 하며, 위임장에도 해당 인감을 찍어야 합니다.",
    "23. (등기필정보 기재) 등기의무자의 권리에 관한 등기필정보(일련번호 및 비밀번호)를 위임장 혹은 신청서 별지에 정확히 기재하거나, 대리인에게 전달해야 합니다.",
    "24. (토지 대장 일치) 토지의 경우 토지대장, 건물의 경우 건축물대장과 등기부등본의 표시가 일치하는지 확인하고 위임장을 작성해야 합니다.",
    "25. (거래가액 기재) 매매로 인한 소유권이전등기 위임장에는 거래신고필증에 기재된 '실제 거래가액'이 등기신청서와 일치하게 반영되어야 합니다.",
    "26. (농지취득자격증명) 농지(전, 답, 과수원)를 취득하는 등기의 경우, 위임장 외에 농지취득자격증명원이 필요함을 인지하고 대리인에게 전달해야 합니다.",
    "27. (근저당권 설정 채무자) 근저당권 설정 위임장 작성 시, '채무자'와 '근저당권설정자(집주인)'가 다를 경우 이를 명확히 구분하여 기재해야 합니다.",
    "28. (채권최고액 기재) 근저당권 설정 시 채권최고액은 아라비아 숫자와 한글(금 일억원 정)을 병기하여 오해의 소지를 없애는 것이 좋습니다.",
    "29. (말소등기 위임) 근저당권 말소등기 위임장에는 해지증서와 함께 등기필증(등기권리증)을 분실했는지 여부를 확인해야 합니다.",
    "30. (상속 등기) 상속 등기 위임장에는 상속인 전원이 날인하거나, 협의분할 상속의 경우 협의서 내용대로 특정 상속인이 위임장을 작성합니다.",
    "31. (증여 등기) 증여로 인한 소유권이전등기 시에는 증여계약서에 검인(구청 등)을 받아야 하므로, 대리인에게 검인 절차도 위임할지 확인해야 합니다.",
    "32. (전세권 설정 범위) 전세권 설정 위임장에는 건물의 전부인지 일부인지(도면 첨부 필요 여부)를 명확히 기재해야 합니다.",
    "33. (대리인의 복대리) 원칙적으로 대리인은 본인의 승낙이나 부득이한 사유가 없으면 복대리인(또 다른 대리인)을 선임하지 못하므로, 위임장에 복대리 허용 문구가 있는지 확인하는 것이 좋습니다.",
    "34. (쌍방대리 허용) 등기신청은 성질상 이익 충돌이 적어, 법무사 등 대리인 1명이 매도인과 매수인 양쪽을 모두 대리(쌍방대리)하는 것이 관행적으로 허용됩니다.",
    "35. (제출기관 확인) 위임장에 기재된 부동산 소재지를 관할하는 '관할 등기소'가 어디인지 확인하고 작성해야 합니다.",
    "36. (등록면허세 등) 대리인이 세금 신고 및 납부를 대행하는 경우, 위임 내용에 '공과금 납부 및 수령에 관한 일체' 문구가 포함되는 것이 좋습니다.",
    "37. (환매특약 등기) 매매와 동시에 환매특약 등기를 할 경우, 별도의 신청서와 위임장이 필요할 수 있으니 주의해야 합니다.",
    "38. (신탁 등기) 부동산 신탁 등기의 경우, 위탁자와 수탁자의 관계 및 신탁원부 작성을 위한 위임 내용이 포함되어야 합니다.",
    "39. (가등기 위임) 가등기 신청 위임장에는 가등기의 목적(소유권이전청구권 보전 등)을 명확히 적어야 합니다.",
    "40. (멸실 등기) 건물이 철거되거나 멸실된 경우, 소유자(등기명의인)의 위임을 받아 1개월 이내에 멸실등기를 신청해야 합니다.",
    "41. (표시변경 등기) 증축 등으로 건물의 면적이 변경된 경우, 건물표시변경등기 위임장을 작성해야 합니다.",
    "42. (등기 명의인 표시 변경) 개명이나 주소 이전에 따른 명의인 표시 변경 등기 위임장은 변경 사실을 증명하는 서면(주민등록초본 등)과 내용이 일치해야 합니다.",
    "43. (수인의 대리인) 대리인이 수인인 경우, 특별한 정함이 없으면 각자가 본인을 대리(각자대리)하게 됩니다.",
    "44. (백지 위임장 주의) 부동산 표시나 위임인 란을 비워둔 채 도장만 찍어주는 '백지 위임장'은 악용될 소지가 있으므로, 반드시 필수 기재사항을 적은 후 날인해야 안전합니다.",
    "45. (작성 용지 규격) 위임장은 가급적 A4 용지 규격에 맞추어 작성하고, 이면지 사용은 피하는 것이 공적 서류로서 적절합니다.",
    "46. (연락처 기재) 등기소로부터 보정 명령 등이 나올 수 있으므로, 위임장에 대리인 또는 본인의 연락처를 정확히 기재하는 것이 유리합니다.",
    "47. (등기 완료 후 수령) 등기 완료 후 등기필정보(권리증)를 대리인이 수령할 수 있도록 위임 범위에 '등기필정보의 수령'을 명시하는 것이 일반적입니다.",
    "48. (비용 부담 명시) 등기 비용(보수, 세금 등)을 누가 부담할 것인지는 위임장 내용과 별도로 당사자 간에 명확히 약정해야 분쟁을 막을 수 있습니다.",
    "49. (사본 보관) 위임장을 작성하여 대리인에게 넘겨주기 전에, 만약의 사태를 대비해 사본(사진, 복사)을 한 부 보관해두는 것이 현명합니다."
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
    today = datetime.date.today()
    current_date_str = today.strftime('%Y년 %m월 %d일')
    system_prompt = f"""
오늘은 {current_date_str}입니다.
당신은 근로기준 전문가입니다.
주어진 팁만을 기반으로 답변하세요.
만약 질문 내용이 [참고 자료]에 없다면, 당신이 가진 일반적인 AI 지식을 활용하여 답변하세요.
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

async def get_building_info(sigungu_cd, bjdong_cd, bun, ji):
    # 키 처리 (한 번 디코딩 시도)
    decoded_key = unquote(BUILDING_API_KEY) 

    params = {
        "serviceKey": decoded_key, 
        "sigunguCd": sigungu_cd,
        "bjdongCd": bjdong_cd,
        "bun": bun.zfill(4),
        "ji": ji.zfill(4),
        "numOfRows": 1,
        "_type": "json" # JSON 달라고 애원해도 에러나면 XML 줍니다.
    }
    
    print(f"📡 [요청 파라미터]: {params}") # 1. 내가 뭘 보냈는지 확인

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(BUILDING_API_URL, params=params, timeout=10.0)
            
            # 2. 서버가 뭐라 했는지 원본 확인 (여기가 핵심!)
            print(f"📨 [국토부 응답 원본]: {response.text}") 

            if response.status_code != 200:
                return None
            
            try:
                data = response.json()
            except json.JSONDecodeError:
                # JSON 변환 실패 = 100% 에러 메시지(XML)가 온 것임
                print("❌ JSON 파싱 실패! 위 [국토부 응답 원본]을 확인하세요.")
                return None

            header_code = data.get("response", {}).get("header", {}).get("resultCode")
            if header_code != "00":
                msg = data.get("response", {}).get("header", {}).get("resultMsg")
                print(f"❌ API 로직 에러: {msg}")
                return None

            items = data.get("response", {}).get("body", {}).get("items", {}).get("item")
            
            if isinstance(items, list) and items:
                return items[0]
            elif isinstance(items, dict):
                return items
            
            return None

    except Exception as e:
        print(f"❌ 예외 발생: {e}")
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

        if field_id == "property_description_text":
            system_prompt += f"""
        
        [주소 추출 특별 규칙]
        - 사용자의 답변에서 '입니다', '이요', '요', '위치해있어요' 같은 서술어와 말꼬리를 제거하세요.
        - 오직 주소 검색 API에 넣을 수 있는 '순수 주소 문자열'만 추출하세요.
        
        [주소 예시]
        Q: 주소가 어디인가요?
        A: 대구 북구 80입니다
        -> filled_fields: {{"{field_id}": "대구 북구 80"}}

        Q: 정확한 주소를 알려주세요.
        A: 서울시 강남구 도곡동 타워팰리스 101동 200호요.
        -> filled_fields: {{"{field_id}": "서울시 강남구 도곡동 타워팰리스 101동 200호"}}
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
    
    # 1. 다음 질문 찾기
    current_item, current_index = find_next_question(content)
    current_bot_question = current_item["question"] if current_item else None
    current_field_id = current_item["field_id"] if current_item else None
    
    # 2. 빈 입력 / 초기 진입 처리
    if not message.strip() or message.strip() == "string":
        user_has_spoken = any(msg.get("sender") == "user" for msg in new_chat_history)
        if not user_has_spoken:
            if current_item:
                return schemas.ChatResponse(
                    reply=current_item["question"], updated_field=None, is_finished=False,
                    full_contract_data=content, chat_history=new_chat_history
                )
        if current_item:
            content[current_item["field_id"]] = ""
            next_item, _ = find_next_question(content)
            reply_text = f"(건너뜁니다)\n{next_item['question']}" if next_item else "모든 항목이 작성되었습니다."
            return schemas.ChatResponse(reply=reply_text, updated_field=[{"field_id": current_item["field_id"], "value": ""}], is_finished=(next_item is None), full_contract_data=content, chat_history=new_chat_history)

    # 3. 채팅 기록 저장
    if current_bot_question:
        new_chat_history.append({"sender": "bot", "message": current_bot_question})
    new_chat_history.append({"sender": "user", "message": message})

    # --------------------------------------------------------------------------
    # ⭐️ [1순위] 주소 확인 단계 (임시 주소가 있을 때만 '네/아니요' 체크)
    # --------------------------------------------------------------------------
    temp_text = content.get("temp_property_text")
    if temp_text and current_field_id == "property_description_text":
        positive_answers = ["네", "예", "맞아요", "맞습니다", "응", "ㅇㅇ", "yes", "ok"]
        negative_answers = ["아니요", "아니", "ㄴㄴ", "no", "놉", "틀렸어", "틀립니다"]
        msg_clean = message.strip().replace(".", "").replace("!", "")

        if any(ans == msg_clean or msg_clean.startswith(ans) for ans in positive_answers):
            content["property_description_text"] = temp_text
            content.pop("temp_property_text", None)
            
            next_item, _ = find_next_question(content)
            reply = next_item['question'] if next_item else "모든 항목이 작성되었습니다."
            new_chat_history.append({"sender": "bot", "message": reply})
            
            return schemas.ChatResponse(reply=reply, updated_field=[{"field_id": "property_description_text", "value": temp_text}], is_finished=(next_item is None), full_contract_data=content, chat_history=new_chat_history)
        
        elif any(word in msg_clean for word in negative_answers):
            reply = "네, 알겠습니다. 수정할 주소를 다시 입력해 주세요."
            new_chat_history.append({"sender": "bot", "message": reply})
            return schemas.ChatResponse(reply=reply, updated_field=None, is_finished=False, full_contract_data=content, chat_history=new_chat_history)

    # --------------------------------------------------------------------------
    # ⭐️ [2순위] 강력한 질문(RAG) 감지 (이게 없어서 자꾸 무시했던 것!)
    # AI 추출보다 먼저 키워드를 검사해서 '세금, 비용' 질문이면 무조건 낚아챕니다.
    # --------------------------------------------------------------------------
    is_rag = False
    rag_keywords = ["세금", "취득세", "비용", "수수료", "얼마", "어떻게", "무엇", "기준", "가요", "나요", "프로", "퍼센트", "?"]
    
    # (A) 키워드 포함 여부 확인
    if any(k in message for k in rag_keywords):
        is_rag = True
    
    # (B) 키워드가 없어도 팁 리스트와 유사도가 높으면 질문으로 간주
    if not is_rag:
        tips, score = await find_top_relevant_tips(message)
        if score >= 0.65: # 유사도 기준
            is_rag = True

    # -----------------------------------------------------------
    # [3순위] AI 데이터 추출 (질문이 아닐 때만 실행)
    # -----------------------------------------------------------
    ai_result = {}
    if not is_rag:
        if current_item is None:
            is_rag = True # 끝났으면 무조건 RAG
        else:
            ai_result = await get_smart_extraction(
                client, current_field_id, message, current_bot_question
            )
            # AI가 직접 "이건 질문이야(rag_required)"라고 했다면 RAG로 변경
            if ai_result.get("status") == "rag_required":
                is_rag = True

    # -----------------------------------------------------------
    # ✅ RAG 답변 처리 (질문인 경우)
    # -----------------------------------------------------------
    if is_rag:
        tips, _ = await find_top_relevant_tips(message)
        rag_answer = await get_rag_response(message, tips)
        
        # 🚨 중요: 팁에 정보가 없어도 "모른다"고 답하고, 폼 입력을 다시 유도해야 함
        new_chat_history.append({"sender": "bot", "message": rag_answer})
        
        if current_item:
            # 질문에 대한 답(또는 모른다는 답)을 하고, 원래 하려던 질문을 다시 붙여줍니다.
            follow = f"\n\n(답변이 되셨나요? 계속해서 진행합니다.)\n{current_item['question']}"
            return schemas.ChatResponse(
                reply=rag_answer + follow, updated_field=None, is_finished=False,
                full_contract_data=content, chat_history=new_chat_history
            )
        else:
            return schemas.ChatResponse(
                reply=rag_answer + "\n\n(추가로 궁금한 점이 있으신가요?)", updated_field=None, is_finished=True,
                full_contract_data=content, chat_history=new_chat_history
            )

    # -----------------------------------------------------------
    # ✅ 폼 데이터 저장 처리 (질문이 아닌 경우)
    # -----------------------------------------------------------
    new_fields = ai_result.get("filled_fields", {})
    
    if current_item:
        # [주소 필드 특수 처리]
        if current_field_id == "property_description_text":
             clean_address = new_fields.get("property_description_text", message)
             full_text = await get_property_text_by_address(clean_address)
             
             # API 실패 시 -> 사용자가 이상한 주소를 넣은 것이므로 안내
             if "찾을 수 없습니다" in full_text or "오류 발생" in full_text:
                 reply = f"입력하신 내용('{clean_address}')으로는 주소를 찾을 수 없습니다.\n정확한 도로명 주소나 지번 주소를 입력해주세요."
                 new_chat_history.append({"sender": "bot", "message": reply})
                 return schemas.ChatResponse(reply=reply, updated_field=None, is_finished=False, full_contract_data=content, chat_history=new_chat_history)
             
             # 성공 시 임시 저장
             content["temp_property_text"] = full_text 
             reply = f"주소를 확인하여 부동산 정보를 불러왔습니다.\n\n[조회 결과]\n{full_text}\n\n정보가 맞다면 '네', 아니라면 정확한 주소를 다시 입력해주세요."
             new_chat_history.append({"sender": "bot", "message": reply})
             
             return schemas.ChatResponse(
                 reply=reply, updated_field=None, is_finished=False,
                 full_contract_data=content, chat_history=new_chat_history
             )
        
        # 일반 필드 저장
        content.update(new_fields)

        # Skip 로직
        skip_n = ai_result.get("skip_next_n_questions", 0)
        for _ in range(skip_n):
            _, idx = find_next_question(content)
            if idx < len(CONTRACT_SCENARIO):
                content[CONTRACT_SCENARIO[idx]["field_id"]] = ""

        # 재질문 처리
        if ai_result.get("status") == "clarify":
            follow_up_q = ai_result.get("follow_up_question")
            new_chat_history.append({"sender": "bot", "message": follow_up_q})
            return schemas.ChatResponse(reply=follow_up_q, updated_field=None, is_finished=False, full_contract_data=content, chat_history=new_chat_history)
        
        if "employee_name" in new_fields:
             content["employee_name_sign"] = new_fields["employee_name"]

    # ✅ 다음 질문 찾기
    next_item, _ = find_next_question(content)
    updated_key = list(new_fields.keys())[0] if new_fields else None
    updated_value = str(new_fields.get(updated_key, "")) if updated_key else ""
    
    if next_item:
        return schemas.ChatResponse(
            reply=next_item["question"],
            updated_field=[{"field_id": updated_key, "value": updated_value}] if updated_key else [],            
            is_finished=False,
            full_contract_data=content,
            chat_history=new_chat_history 
        )
    else:
        return schemas.ChatResponse(
            reply="모든 항목이 작성되었습니다.",
            updated_field=[{"field_id": updated_key, "value": updated_value}] if updated_key else None,
            is_finished=True,
            full_contract_data=content,
            chat_history=new_chat_history 
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