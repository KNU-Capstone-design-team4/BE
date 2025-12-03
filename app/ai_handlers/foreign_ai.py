import os
import json
import uuid
import datetime
import numpy as np
import asyncio
import re
from pathlib import Path
from typing import Dict, Optional, Any, Tuple, List
from openai import AsyncOpenAI
from docxtpl import DocxTemplate
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas

client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# --- 1. 통합신청서 전용 시나리오 ---
# (미리 작성해두신 '통합신청서' 질문 리스트를 여기에 붙여넣으세요.)
# ❗️ field_id는 1단계에서 만든 .docx 템플릿의 {{ 변수명 }}과 일치해야 합니다.
CONTRACT_SCENARIO = [
    {"field_id": "surname", "question": "여권상의 성(Surname)을 영문으로 알려주세요."},
    {"field_id": "given_names", "question": "여권상의 이름(Given names)을 영문으로 알려주세요."},
    {"field_id": "birth", "question": "생년월일을 알려주세요.(yyyy-mm-dd 형식)"},
    {"field_id": "sex", "question": "성별을 알려주세요. (남 / 여)"},
    {"field_id": "nation", "question": "국적을 알려주세요."},
    {"field_id": "passport_num", "question": "여권번호를 알려주세요."},
    {"field_id": "passport_date", "question": "여권 발급일자를 알려주세요."},
    {"field_id": "passport_expired", "question": "여권 유효기간을 알려주세요."},
    {"field_id": "korea_address", "question": "대한민국 내 주소를 알려주세요."},
    {"field_id": "tele_num", "question": "전화 번호를 알려주세요. (예: 02-123-4567)"},
    {"field_id": "phone_num", "question": "휴대 전화 번호를 알려주세요. (예: 010-1234-5678)"},
    {"field_id": "address_in_home_country", "question": "본국 주소를 알려주세요."},
    {"field_id": "email", "question": "이메일을 알려주세요"},
    {"field_id": "refund_bank_account", "question": "반환용 계좌번호를 알려주세요 (필요시)"},
    {"field_id": "foreign_num", "question": "본인의 외국인 등록번호를 알려주세요(총 13자리)"},

    # --- 2. 신청 항목 (첫 번째 분기점) ---
    {"field_id": "application_type", "question": "신청/신고 항목을 선택해주세요. (1. 외국인 등록, 2. 등록증 재발급, 3. 체류기간 연장허가, 4. 체류자격 변경허가, 5. 체류자격 부여,6. 체류자격외 활동허가, 7. 근무처 변경/추가허가, 8. 체류지 변경신고, 9. 등록사항 변경신고)"},
    
    # 2-1. [조건부 질문 1] '체류자격 변경허가' 선택 시
    {"field_id": "app_change_desired", "question": "변경을 희망하는 체류 자격은 무엇인가요? (예: E-7)"},
    # 2-2. [조건부 질문 2] '체류자격 부여' 선택 시
    {"field_id": "app_grant_desired", "question": "부여받고자 하는 체류 자격은 무엇인가요?"},
    # 2-3. [조건부 질문 3] '체류자격외 활동허가' 선택 시
    {"field_id": "app_other_desired", "question": "허가받고자 하는 활동의 내용은 무엇인가요?"},
    
    # --- 3. 직업 (두 번째 분기점) ---
    {"field_id": "occupation_type", "question": "현재 직업이 '학생'인가요, '근무자'인가요, 아니면 둘 다 아닌가요?"},

    # 3-1. [조건부 질문 4] '학생' 선택 시
    {"field_id": "school_status", "question": "재학여부를 알려주세요.(미취학, 초, 중, 고)"},
    {"field_id": "school_type", "question": "학교 종류를 알려주세요(교육청 인가, 교육청 비인가, 대안학교)"},
    {"field_id": "school_name", "question": "학교이름을 알려주세요"},
    {"field_id": "school_phone", "question": "학교 전화번호를 알려주세요."},    

    # 3-2. [조건부 질문 5] '근무자' 선택 시
    {"field_id": "current_workspace", "question": "이전까지 일하던 근무처(회사명)를 알려주세요."},
    {"field_id": "cur_business_regis_num", "question": "이전까지 일했던 근무처의 사업자등록 번호를 알려주세요."},
    {"field_id": "cur_phone", "question": "이전까지 일했던 근무처의 전화번호를 알려주세요."},
    
    {"field_id": "new_workplace", "question": "앞으로 일할 근무처(회사명)를 알려주세요."},
    {"field_id": "new_business_regis_num", "question": "앞으로 일할 근무처의 사업자등록 번호를 알려주세요."},
    {"field_id": "new_phone", "question": "앞으로 일할 근무처의 전화번호를 알려주세요."},
    {"field_id": "occupation", "question": "현재 직업(직종)을 알려주세요."},
    {"field_id": "annual_income", "question": "연 소득 금액을 만원 단위로 알려주세요."},
    
    {"field_id": "intended_period_reentry", "question": "재입국 신청기간을 알려주세요."}

]

TIP_LIST = [
    "1. (외국인의 입국-제7조) 외국인이 입국할 때에는 유효한 여권과 법무부장관이 발급한 사증(査證)을 가지고 있어야 한다.",
    "2. (외국인의 입국-제7조)재입국 허가를 받았거나 면제된 기간이 끝나기 전에 입국하는 외국인, 사증면제협정을 체결한 국가의 국민, 대통령령으로 정하는 바에 따라 따로 입국허가를 받은 국제친선·관광 목적의 외국인, 또는 난민여행증명서 유효기간 내에 입국하는 외국인은 사증(비자) 없이 입국할 수 있다.",
    "3. (외국인의 입국-제7조)법무부장관은 공공질서의 유지나 국가이익에 필요하다고 인정하면 제2항제2호에 해당하는 사람에 대하여 사증면제협정의 적용을 일시 정지할 수 있다.",
    "4. (외국인의 입국-제7조)대한민국과 수교(修交)하지 아니한 국가나 법무부장관이 외교부장관과 협의하여 지정한 국가의 국민은 제1항에도 불구하고 대통령령으로 정하는 바에 따라 재외공관의 장이나 지방출입국ㆍ외국인관서의 장이 발급한 외국인입국허가서를 가지고 입국할 수 있다.",
    "5. (체류자격-제10조)입국 외국인은 대한민국에 체류 기간이 제한되는 일반체류자격이나 영주(永住)할 수 있는 영주자격 중 어느 하나를 가져야 한다.",
    "6. (체류자격-제10조)일반체류자격은 관광, 방문 등의 목적으로 90일 이하의 기간 동안 머물 수 있는 단기체류자격과 유학, 연수, 투자, 주재, 결혼 등의 목적으로 90일을 초과하여 법무부령으로 정하는 기간 동안 거주할 수 있는 장기체류자격으로 구분되며, 이 두 체류자격의 종류, 해당 대상 또는 활동 범위는 체류목적이나 취업활동 가능 여부 등을 고려하여 대통령령으로 정한다.",
    "7. (체류자격-제10조)영주자격을 가진 외국인은 활동범위 및 체류기간의 제한을 받지 않으며, 이 영주자격을 취득하려는 사람은 대통령령으로 정하는 자격에 부합해야 하고, 법령 준수 등의 품행 단정, 생계 유지 능력, 한국어 능력 및 한국 사회에 대한 이해 등의 기본 소양 요건을 모두 갖추어야 하지만, 법무부장관은 특별 공로자나 특정 분야 탁월 능력자, 일정 금액 이상 투자자 등 대통령령으로 정하는 사람에 대해서는 생계 유지 능력 및 기본 소양 요건의 전부 또는 일부를 완화하거나 면제할 수 있고, 이 요건들의 기준과 범위 등 세부 사항은 법무부령으로 정한다.",
    "8. (사전여행허가-제7조의 3)법무부장관은 공공질서 유지나 국가이익을 위해 필요하다고 인정하는 경우, 사증면제협정국 국민이나 무사증입국이 허가된 외국인 등 특정 외국인에 대해 입국 전 사전여행허가를 받도록 할 수 있으며, 허가를 받은 외국인은 입국 시 사전여행허가서를 지참해야 하고, 이 허가서 발급에 필요한 기준, 절차 및 방법은 법무부령으로 정한다.",
    "9. (허위초청금지-제7조의2)누구든지 외국인을 입국시키기 위해 거짓된 사실 기재나 거짓된 신원보증 등 부정한 방법으로 외국인을 초청하거나 그 초청을 알선하는 행위, 또는 거짓으로 사증이나 사증발급인정서를 신청하거나 그러한 신청을 알선하는 행위를 해서는 안 된다.",
    "10. (사증-8조)제7조에 따른 사증은 1회만 입국 가능한 단수사증(單數査證)과 2회 이상 입국 가능한 복수사증(複數査證)으로 구분되며, 법무부장관은 사증 발급 권한을 대통령령에 따라 재외공관의 장에게 위임할 수 있고, 그 발급 기준 및 절차는 법무부령으로 정한다.",
    "11. (사증발급인증서-9조)법무부장관은 사증을 발급하기 전에 특히 필요하다고 인정할 경우 입국하려는 외국인의 신청을 받아 사증발급인정서를 발급할 수 있으며, 이 신청은 외국인을 초청하려는 자가 대리할 수 있고, 인정서의 발급 대상, 기준 및 절차는 법무부령으로 정한다.",
    "12. (영주자격자의 활동범위-제10조의3호)제10조제2호에 따른 영주자격(이하 “영주자격”이라 한다)을 가진 외국인은 활동범위 및 체류기간의 제한을 받지 아니한다.",
    "13. (입국금지-제11조)법무부장관은 감염병 환자, 마약류 중독자, 총포ㆍ도검 등을 위법하게 소지한 사람, 대한민국의 이익이나 공공의 안전 및 선량한 풍속을 해칠 염려가 있는 사람, 구호(救護)가 필요한 정신장애인이나 체류 비용 부담 능력이 없는 사람, 강제퇴거 후 5년이 지나지 않은 사람, 과거 인권 학살에 관여한 사람, 그리고 그 밖에 법무부장관이 입국 부적당하다고 인정하는 사람에 대하여 입국을 금지할 수 있으며, 입국하려는 외국인의 본국이 상호주의 원칙에 따라 자국민 입국을 거부하는 경우에도 동일한 사유로 그 외국인의 입국을 거부할 수 있다.",
    "14. (입국심사 의무-제12조 1항)외국인이 입국하려는 경우에는 입국하는 출입국항에서 대통령령으로 정하는 바에 따라 여권과 입국신고서를 출입국관리공무원에게 제출하여 입국심사를 받아야 한다.",
    "15. (입국 허가 요건-제12조 3항)출입국관리공무원은 입국심사 시 여권 및 이 법에서 요구하는 사증이 유효하고, 사전여행허가서(제7조의3제2항에 따름)가 유효하며, 입국 목적이 체류자격에 맞고, 체류 기간이 법무부령에 따라 정해졌을 뿐만 아니라, 제11조에 따른 입국 금지 또는 거부 대상이 아닐 경우에 한하여 입국을 허가한다.",
    "16. (입국 시 생체정보 제공 의무- 제12조2 제1항)입국하려는 외국인은 제12조에 따른 입국심사를 받을 때 법무부령으로 정하는 방법으로 생체정보를 제공하고 본인 확인 절차에 응해야 하나, 17세 미만인 사람, 외국 정부나 국제기구 업무 수행을 위해 입국하는 사람 및 그 동반 가족, 그리고 우호 증진 및 경제활동 촉진 등을 고려하여 대통령령으로 생체정보 제공을 면제하는 것이 필요하다고 정하는 사람에 대해서는 예외로 한다.",
    "17. (입국 시 생체정보 제공 의무- 제12조2)출입국관리공무원은 외국인이 제1항 본문에 따라 생체정보를 제공하지 아니하는 경우에는 그의 입국을 허가하지 아니할 수 있다.",
    "18. (입국 시 생체정보 제공 의무- 제12조2) 법무부장관은 입국심사에 필요한 경우에는 관계 행정기관이 보유하고 있는 외국인의 생체정보의 제출을 요청할 수 있다.",
    "19. (선박등의 제공금지-제12조의3)누구든지 외국인을 불법으로 입국 또는 출국시키거나 대한민국을 거쳐 다른 국가에 불법으로 입국시키려는 목적으로 선박 등이나 여권, 사증, 탑승권 및 그 밖에 출입국에 사용될 수 있는 서류나 물품을 제공하거나, 이러한 행위를 알선해서는 안 된다.",
    "20. (선박등의 제공금지-제12조의3)누구든지 불법으로 입국한 외국인을 대한민국에서 은닉하거나 도피하게 하거나 그러한 목적으로 교통수단을 제공하는 행위, 또는 이러한 행위를 알선해서는 안 된다.",
    "21. (조건부 입국허가 –제13조)지방출입국ㆍ외국인관서의 장은 부득이한 사유로 제12조제3항제1호의 요건을 갖추지 못하였으나 일정 기간 내에 갖출 수 있다고 인정되는 사람, 제11조제1항 각 호에 해당된다고 의심되거나 제12조제3항제2호의 요건을 갖추지 못하였다고 의심되어 특별히 심사할 필요가 있는 사람, 또는 그 밖에 조건부 입국을 허가할 필요가 있다고 인정되는 사람에 대해서는 대통령령으로 정하는 바에 따라 조건부 입국을 허가할 수 있다.",
    "22. (외국인의 체류 및 활동범위-제17조)외국인은 그 체류자격과 체류기간의 범위에서 대한민국에 체류할 수 있다.",
    "23. (외국인의 체류 및 활동범위-제17조)대한민국에 체류하는 외국인은 이 법 또는 다른 법률에서 정하는 경우를 제외하고는 정치활동을 하여서는 아니 된다.",
    "24. (외국인의 체류 및 활동범위-제17조) 법무부장관은 대한민국에 체류하는 외국인이 정치활동을 하였을 때에는 그 외국인에게 서면으로 그 활동의 중지명령이나 그 밖에 필요한 명령을 할 수 있다.",
    "25. (외국인 고용의 제한-제18조 1항) 외국인이 대한민국에서 취업하려면 대통령령으로 정하는 바에 따라 취업활동을 할 수 있는 체류자격을 받아야 한다.",
    "26. (외국인 고용의 제한-제18조) 제1항에 따른 체류자격을 가진 외국인은 지정된 근무처가 아닌 곳에서 근무하여서는 아니 된다.",
    "27. (외국인 고용의 제한-제18조) 누구든지 제1항에 따른 체류자격을 가지지 아니한 사람을 고용하여서는 아니 된다.",
    "28. (외국인 고용의 제한-제18조) 누구든지 제1항에 따른 체류자격을 가지지 아니한 사람의 고용을 알선하거나 권유하여서는 아니 된다.",
    "29. (외국인 고용의 제한-제18조) 누구든지 제1항에 따른 체류자격을 가지지 아니한 사람의 고용을 알선할 목적으로 그를 자기 지배하에 두는 행위를 하여서는 아니 된다.",
    "30. (활동범위의 제한-제22조) 법무부장관은 공공의 안녕질서나 대한민국의 중요한 이익을 위하여 필요하다고 인정하면 대한민국에 체류하는 외국인에 대하여 거소(居所) 또는 활동의 범위를 제한하거나 그 밖에 필요한 준수사항을 정할 수 있다.",
    "31. (체류자격 부여-제23조) 대한민국에서 출생한 외국인은 출생한 날부터 90일 이내에, 체류 중 대한민국 국적을 상실하거나 이탈하는 등 그 밖의 사유가 발생한 외국인은 사유 발생일로부터 60일 이내에 제10조에 따른 체류자격을 가지지 못하게 된 경우 대통령령으로 정하는 바에 따라 체류자격을 받아야 하며, 그 부여의 심사 기준은 법무부령으로 정한다.",
    "32. (체류자격 변경 허가-제24조)대한민국에 체류하는 외국인이 그 체류자격과 다른 체류자격에 해당하는 활동을 하려면 대통령령으로 정하는 바에 따라 미리 법무부장관의 체류자격 변경허가를 받아야 한다.",
    "33. (체류기간 연장 허가-제25조)외국인이 체류기간을 초과하여 계속 체류하려면 대통령령으로 정하는 바에 따라 체류기간이 끝나기 전에 법무부장관의 체류기간 연장허가를 받아야 한다.",
    "34. (결혼이민자 등에 대한 특칙-제25조의2) 법무부장관은 가정폭력, 성폭력범죄, 아동학대범죄 또는 인신매매 등 피해를 이유로 법원의 재판, 수사기관의 수사 또는 그 밖의 법률에 따른 권리구제 절차가 진행 중인 외국인(가정폭력 피해의 경우 대한민국 국민의 배우자인 외국인, 아동학대의 경우 아동 및 보호자)이 체류기간 연장허가를 신청하는 경우 해당 절차가 종료할 때까지 연장을 허가할 수 있으며, 그 기간 만료 이후에도 피해 회복 등을 위해 필요하다고 인정하면 추가로 체류기간 연장을 허가할 수 있다.",
    "35. (여권등의 휴대의무-제27조)대한민국에 체류하는 외국인은 항상 여권ㆍ선원신분증명서ㆍ외국인입국허가서ㆍ외국인등록증ㆍ모바일외국인등록증 또는 상륙허가서(이하 “여권등”이라 한다)를 지니고 있어야 한다. 다만, 17세 미만인 외국인의 경우에는 그러하지 아니하다.",
    "36. (여권등의 제시 의무-제27조 제2항)외국인은 출입국관리공무원이나 권한 있는 공무원이 그 직무수행과 관련하여 여권등의 제시를 요구하면 여권등을 제시하여야 한다.",
    "37. (출국심사-제28조)외국인이 출국할 때에는 유효한 여권을 가지고 출국하는 출입국항에서 출입국관리공무원의 출국심사를 받아야 한다.",
    "38. (출국금지-제4조 1항)법무부장관은 형사재판 계속 중인 사람, 징역형이나 금고형 집행이 끝나지 않은 사람, 대통령령으로 정하는 금액 이상의 벌금·추징금 또는 국세·관세·지방세를 정당한 사유 없이 납부 기한까지 내지 않은 사람, 「양육비 이행확보 및 지원에 관한 법률」에 따른 양육비 채무자 중 심의ㆍ의결을 거친 사람, 「근로기준법」에 따라 명단이 공개된 체불사업주, 그리고 그 밖에 대한민국의 이익이나 공공의 안전 또는 경제질서를 해칠 우려가 있어 법무부령으로 출국이 적당하지 않다고 정하는 사람에 대하여 6개월 이내의 기간을 정하여 출국을 금지할 수 있다.",
    "39. (출국금지-제4조 2항)법무부장관은 범죄 수사를 위해 출국이 적당하지 않다고 인정되는 사람에 대하여는 1개월 이내의 기간을 정하여 출국을 금지할 수 있으나, 소재를 알 수 없거나 도주 등 특별한 사유로 수사 진행이 어려운 사람은 3개월 이내로, 기소중지 또는 수사중지 상태에서 체포영장 또는 구속영장이 발부된 사람은 영장 유효기간 이내로 그 기간을 정한다.",
    "40. (재입국허가-제30조) 법무부장관은 외국인등록을 하거나 등록이 면제된 외국인이 체류 기간 내에 출국했다가 재입국하려는 경우 신청을 받아 재입국을 허가할 수 있으며, 이 허가는 1회 입국 가능한 단수재입국허가와 2회 이상 입국 가능한 복수재입국허가로 구분되지만, 영주자격자나 법무부령으로 정하는 재입국허가 면제 사유가 있는 사람에 대해서는 허가를 면제할 수 있다.",
    "41. (재입국허가-재30조)외국인이 질병 등 부득이한 사유로 허가 기간 내에 재입국할 수 없을 때에는 기간이 끝나기 전에 법무부장관의 연장 허가를 받아야 하며, 법무부장관은 이 기간 연장 허가 권한을 대통령령에 따라 재외공관의 장에게 위임할 수 있고, 재입국 허가 및 그 기간 연장, 면제에 관한 기준과 절차는 법무부령으로 정한다.",
    "42. (외국인등록-제31조 제1항)외국인이 입국한 날부터 90일을 초과하여 대한민국에 체류하려면 대통령령으로 정하는 바에 따라 입국한 날부터 90일 이내에 그의 체류지를 관할하는 지방출입국ㆍ외국인관서의 장에게 외국인등록을 하여야 한다. 다만, 다음 각 호의 어느 하나에 해당하는 외국인의 경우에는 그러하지 아니하다",
    "43. (외국인등록번호 부여-제31조 제5항)지방출입국ㆍ외국인관서의 장은 제1항부터 제4항까지의 규정에 따라 외국인등록을 한 사람에게는 대통령령으로 정하는 방법에 따라 개인별로 고유한 등록번호(이하 “외국인등록번호”라 한다)를 부여하여야 한다.",
    "44. (외국인 등록사항-제32조) 외국인등록사항은 성명, 성별, 생년월일 및 국적, 여권의 번호·발급일자 및 유효기간, 근무처와 직위 또는 담당 업무, 본국의 주소와 국내 체류지, 체류자격과 체류 기간, 그리고 이 외에 법무부령으로 정하는 사항들로 구성된다.",
    "45. (외국인 등록증의 발급-제33조 제1항)제31조에 따라 외국인등록을 받은 지방출입국ㆍ외국인관서의 장은 대통령령으로 정하는 바에 따라 그 외국인에게 외국인등록증을 발급하여야 한다. 다만, 그 외국인이 17세 미만인 경우에는 발급하지 아니할 수 있다.",
    "46. (모바일외국인등록증 발급-제33`조6항) 지방출입국ㆍ외국인관서의 장은 제1항에 따라 외국인등록증을 발급받은 외국인에게 외국인등록증과 동일한 효력을 가진 모바일외국인등록증(「전기통신사업법」 제2조제20호에 따른 이동통신단말장치에 암호화된 형태로 설치된 외국인등록증을 말한다. 이하 같다)을 발급할 수 있다.",
    "47. (외국인등록사항의 변경신고-제35조)제31조에 따라 등록을 한 외국인은 성명, 성별, 생년월일 및 국적, 여권의 번호, 발급일자 및 유효기간, 그리고 그 밖에 법무부령으로 정하는 사항이 변경되었을 경우 대통령령으로 정하는 바에 따라 15일 이내에 체류지 관할 지방출입국ㆍ외국인관서의 장에게 외국인등록사항 변경신고를 해야 한다.",
    "48. (체류지 변경의 신고-제36조 제1항)제31조에 따라 등록을 한 외국인이 체류지를 변경하였을 때에는 대통령령으로 정하는 바에 따라 전입한 날부터 15일 이내에 새로운 체류지의 시ㆍ군ㆍ구 또는 읍ㆍ면ㆍ동의 장이나 그 체류지를 관할하는 지방출입국ㆍ외국인관서의 장에게 전입신고를 하여야 한다.",
    "49. (외국인 등록증의 반납-제37조 제1항) 제31조에 따라 등록한 외국인이 출국할 때에는 출입국관리공무원에게 외국인등록증을 반납해야 하지만, 재입국허가를 받고 허가기간 내에 다시 입국하려는 경우, 복수사증 소지자나 재입국허가 면제대상 국가 국민으로서 체류기간 내에 다시 입국하려는 경우, 또는 난민여행증명서를 받고 유효기간 내에 다시 입국하려는 경우에는 그러하지 아니하다.",
    "50. (생체정보의 제공 의무-제38조 제1항) 법무부장관은 제31조에 따라 외국인등록을 하거나 「재외동포의 출입국과 법적 지위에 관한 법률」에 따라 국내거소신고를 하려는 17세 이상인 사람, 이 법이나 다른 법률을 위반하여 조사를 받거나 수사를 받고 있는 사람, 신원이 확실하지 않은 사람, 또는 대한민국의 안전이나 이익 등을 위하여 법무부장관이 특히 필요하다고 인정하는 사람에 대해서는 법무부령으로 정하는 바에 따라 생체정보를 제공하도록 하여야.",
    "51. (외국인의 정보제공 의무-제81조의3 제1항) 제10조의2제1항제1호에 따른 단기체류자격을 가진 외국인(이하 “숙박외국인”이라 한다)은 「감염병의 예방 및 관리에 관한 법률」에 따른 위기경보의 발령 또는 「국민보호와 공공안전을 위한 테러방지법」에 따른 테러경보의 발령 등 법무부령으로 정하는 경우에 한정하여 다음 각 호의 어느 하나에 해당하는 자(이하 “숙박업자”라 한다)가 경영하는 숙박업소에서 머무는 경우 숙박업자에게 여권 등 법무부령으로 정하는 자료를 제공하여야 한다."
]

# 0.4로 설정하니깐 폼 답변인데 rag질문으로 인식되는 문제가 자주 발생해서 0.7로 높였음
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
당신은 대한민국 출입국관리법 및 체류허가 업무에 전문 지식을 가진 
'출입국·외국인정책 전문가 AI 상담관'입니다.

당신의 답변은 반드시 아래의 '참고 자료(팁 목록)'에 기반하여야 합니다.
(즉, TIP_LIST에 없는 내용은 단정적으로 말하지 말고, "참고 자료의 범위 내에서…"라고 제한적으로 표현)

--- 참고 자료(통합신청서 관련 TIP) ---
{relevant_tips}
-----------------------------------------

[답변 규칙]

1. 당신의 역할은 통합신청서(외국인등록, 체류기간 연장, 체류자격 변경/부여, 근무처 변경·추가, 체류지 변경 등) 작성·신고와 관련된 사항만 전문적으로 답변하는 것입니다.

2. 아래 PDF 서식(통합신청서/신고서)을 기준으로, 사용자의 질문이 어떤 항목(application type), 어떤 서류, 어떤 절차와 관련된 것인지 판단하고 안내하세요.

3. 답변은 반드시 아래 순서를 따릅니다:
   (1) 질문에서 파악한 핵심 쟁점을 정리  
   (2) 참고 자료(TIP_LIST)에 근거하여 답변  
   (3) 필요하면 “추가적으로 통합신청서의 해당 항목은 …에 해당합니다"처럼 안내  
   (4) 마지막 줄에 '출처: 팁 N번' 형식으로 근거 명시

4. 모르면 모른다고 답하고, TIP_LIST의 범위를 벗어나는 법적 판단은 하지 마세요.
   (예: 필요 서류, 심사 기준, 허가 가능 여부는 TIP_LIST에 기반해 제한적으로만 답변)

5. 불필요한 사족, 인사말, 문장 외의 요소는 넣지 말고 답변만 하세요.

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


# --- 2. 통합신청서 전용 AI 추출기 ---
async def get_smart_extraction(
    client: AsyncOpenAI,
    field_id: str, 
    user_message: str, 
    question: str
) -> Dict:
    """
    [통합신청서 AI 스마트 추출기]
    '통합신청서'의 복잡한 폼(체크박스, 날짜 등)을 채우기 위해 
    working_ai.py의 프롬프트 구조를 재사용합니다.
    """
    
    today = datetime.date.today()
    current_year = today.year
    json_format_example = '{"status": "...", "filled_fields": {"key": "value", ...}, "skip_next_n_questions": 0, "follow_up_question": null}'
    
    # ❗️ [수정] 기본 프롬프트의 역할 수정
    base_system_prompt = f"""
    당신은 대한민국 '출입국관리사무소'의 민원 서류 작성을 돕는 전문 AI 어시스턴트입니다.
    사용자의 답변에서 '통합신청서' 서식에 필요한 핵심 정보를 추출해야 합니다.
    오늘은 {today.strftime('%Y년 %m월 %d일')}입니다. (현재 연도는 {current_year}년)

    [규칙]
    1.  `filled_fields`에는 템플릿(`.docx`)의 변수명(field_id)을 key로 사용하여 추출한 값을 채워야 합니다.
    2.  `skip_next_n_questions`는 사용자의 답변으로 인해 불필요해진 *다음* 질문들의 '개수'입니다. (분기 로직의 핵심)
    3.  [이름]은 사용자 입력을 영어로 변경하지 않는다. 사용자 입력이 영어인지 검증하여 한국어라면 다시 입력받는다. 
    3.  [생년월일] 형식은 'YYYY', 'MM', 'DD'로 분리하여 저장해야 합니다.
    4.  [성별]은 'sex_m_check', 'sex_f_check' 변수에 true 또는 false로 채워야 합니다.
    5.  [신청 항목]은 10개의 'fore_resident_regis', 're_regis_card' 등의 변수에 true 또는 false로 채워야 합니다.
    6.  [직업] (occupation_type) 질문은 사용자 답변을 저장하지 않습니다.
    7.  [재학여부]는 'non', 'ele', 'mid', 'hi' 변수에 true 또는 false로 채워야 합니다.
    8.  [학교종류]는 'ac', 'no_ac', 'alt' 변수에 true 또는 false로 채워야 합니다.
    9.  *중요*: 스킵하는 필드들에는 빈 문자열 ""을 채워서 docx 템플릿의 {{변수}} 태그가 남지 않게 해야 합니다.
    10. 반드시 지정된 JSON 형식으로만 반환해야 합니다.
    11. 만약 사용자가 봇의 질문에 대답하지 않고, **법률적 질문, 절차 문의, 용어 정의** 등을 물어본다면:
        - 'status'를 "rag_required"로 설정하세요.
        - 'filled_fields'는 빈 딕셔너리로 두세요.
        - 'follow_up_question'은 'null'로 두세요.
        (예: "외국인 등록증이 꼭 필요한가요?", "수수료는 얼마인가요?", "이게 무슨 뜻인가요?")

    [JSON 반환 형식]
    {json_format_example}
    """
    
    specific_examples = ""
    
    # ❗️ [필수 수정] 
    # '통합신청서'의 field_id에 맞춰 퓨샷(Few-Shot) 예시를 새로 만들어야 합니다.
    # 특히 체크박스 필드들은 반드시 예시가 필요합니다.
    
    # [생년월일] -> 년, 월, 일로 쪼개기
    if field_id == "birth":
        specific_examples = f"""
        [예시 1: 날짜 형식화 (YYYY, MM, DD로 분리)]
        question: "{question}"
        user_message: "1990년 1월 30일입니다."
        AI: {{"status": "success", "filled_fields": {{"birth_yyyy": "1990", "birth_mm": "01", "birth_dd": "30"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """
        
    # [성별] -> 체크박스로 변환
    elif field_id == "sex":
        specific_examples = """
        [예시 1: '남' 선택]
        question: "성별을 알려주세요. (남 / 여)"
        user_message: "남자입니다"
        AI: {{"status": "success", "filled_fields": {{"sex_m_check": true, "sex_f_check": false}}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 2: '여' 선택]
        question: "성별을 알려주세요. (남 / 여)"
        user_message: "여자"
        AI: {{"status": "success", "filled_fields": {{"sex_m_check": false, "sex_f_check": true}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """
  # [분기 1: 신청 항목]
    elif field_id == "application_type":
        # ❗️ [중요] 시나리오 리스트(1단계)를 기준으로 '건너뛸 질문의 개수'를 정확히 계산해야 합니다.
        # 예: '체류자격 변경/부여/외활동허가' 질문(3개)
        #     '직업' 질문(1개)
        #     '학생' 질문(3개)
        #     '근무자' 질문(4개)
        #     '근무처 변경' 질문(2개)
        # ...
        # (이 예시에서는 '희망 자격' 관련 질문 3개를 건너뛴다고 가정합니다)
        skip_count_for_simple_app = 3 
        
        # 기본값 false
        all_app_fields_unselected = {
            "fore_resident_regis": False, "re_regis_card": False, "ex_sojo_peri": False,
            "chg_stus_sojo": False, "grant_sojourm": False, "engage_act_not_sojo": False,
            "chg_add_wrkplc": False, "reen_permit": False, "alt_residence": False, "chg_registration": False
        }
                
        # (A) 단순 스킵 (skip: 3) 항목 7개
        fields_for_reg = all_app_fields_unselected.copy()
        fields_for_reg["fore_resident_regis"] = True
        
        fields_for_reissue = all_app_fields_unselected.copy()
        fields_for_reissue["re_regis_card"] = True
        
        fields_for_extension = all_app_fields_unselected.copy()
        fields_for_extension["ex_sojo_peri"] = True
        
        fields_for_workplace = all_app_fields_unselected.copy()
        fields_for_workplace["chg_add_wrkplc"] = True
        
        fields_for_reentry = all_app_fields_unselected.copy()
        fields_for_reentry["reen_permit"] = True
        
        fields_for_alt_res = all_app_fields_unselected.copy()
        fields_for_alt_res["alt_residence"] = True
        
        fields_for_chg_reg = all_app_fields_unselected.copy()
        fields_for_chg_reg["chg_registration"] = True

        # (B) 조건부 질문 (skip: 0, 1, 2) 항목 3개
        fields_for_change = all_app_fields_unselected.copy()
        fields_for_change["chg_stus_sojo"] = True

        fields_for_grant = all_app_fields_unselected.copy()
        fields_for_grant["grant_sojourm"] = True

        fields_for_other = all_app_fields_unselected.copy()
        fields_for_other["engage_act_not_sojo"] = True
        
        # --- 10개 항목 전체에 대한 예시 프롬프트 생성 ---
        specific_examples = f"""
        [템플릿 변수명 목록] (총 10개)
        "fore_resident_regis", "re_regis_card", "ex_sojo_peri", "chg_stus_sojo", "grant_sojourm", "engage_act_not_sojo", "chg_add_wrkplc", "reen_permit", "alt_residence", "chg_registration"

        [예시 1: '외국인 등록' (단순 스킵 3)]
        question: "{question}"
        user_message: "1번 외국인 등록이요"
        AI: {{"status": "success", "filled_fields": {json.dumps(fields_for_reg)}, "skip_next_n_questions": {skip_count_for_simple_app}, "follow_up_question": null}}

        [예시 2: '등록증 재발급' (단순 스킵 3)]
        question: "{question}"
        user_message: "등록증 재발급"
        AI: {{"status": "success", "filled_fields": {json.dumps(fields_for_reissue)}, "skip_next_n_questions": {skip_count_for_simple_app}, "follow_up_question": null}}
        
        [예시 3: '체류기간 연장' (단순 스킵 3)]
        question: "{question}"
        user_message: "체류기간 연장허가"
        AI: {{"status": "success", "filled_fields": {json.dumps(fields_for_extension)}, "skip_next_n_questions": {skip_count_for_simple_app}, "follow_up_question": null}}

        [예시 4: '체류자격 변경' (스킵 0)]
        question: "{question}"
        user_message: "체류자격 변경허가 신청할게요"
        AI: {{"status": "success", "filled_fields": {json.dumps(fields_for_change)}, "skip_next_n_questions": 0, "follow_up_question": null}}
        
        [예시 5: '체류자격 부여' (스킵 1)]
        question: "{question}"
        user_message: "자격 부여"
        AI: {{"status": "success", "filled_fields": {json.dumps(fields_for_grant)}, "skip_next_n_questions": 1, "follow_up_question": null}}

        [예시 6: '체류자격외 활동' (스킵 2)]
        question: "{question}"
        user_message: "6번이요"
        AI: {{"status": "success", "filled_fields": {json.dumps(fields_for_other)}, "skip_next_n_questions": 2, "follow_up_question": null}}
        
        [예시 7: '근무처 변경' (단순 스킵 3)]
        question: "{question}"
        user_message: "근무처 변경 신고"
        AI: {{"status": "success", "filled_fields": {json.dumps(fields_for_workplace)}, "skip_next_n_questions": {skip_count_for_simple_app}, "follow_up_question": null}}
        
        [예시 8: '재입국 허가' (단순 스킵 3)]
        question: "{question}"
        user_message: "재입국 허가"
        AI: {{"status": "success", "filled_fields": {json.dumps(fields_for_reentry)}, "skip_next_n_questions": {skip_count_for_simple_app}, "follow_up_question": null}}
        
        [예시 9: '체류지 변경' (단순 스킵 3)]
        question: "{question}"
        user_message: "체류지 변경"
        AI: {{"status": "success", "filled_fields": {json.dumps(fields_for_alt_res )}, "skip_next_n_questions": {skip_count_for_simple_app}, "follow_up_question": null}}
        
        [예시 10: '등록사항 변경' (단순 스킵 3)]
        question: "{question}"
        user_message: "등록사항 변경 신고"
        AI: {{"status": "success", "filled_fields": {json.dumps(fields_for_chg_reg )}, "skip_next_n_questions": {skip_count_for_simple_app}, "follow_up_question": null}}
        """
       
    # --------------------------------------------------------------------
    # [신규 추가] 분기 1-1: '체류자격 변경' 희망 자격
    # (application_type에서 이 질문으로 넘어옴)
    # (이 질문에 답하면, 남은 조건부 질문 2개(app_grant, app_other)를 스킵)
    # --------------------------------------------------------------------
    elif field_id == "app_change_desired":
        specific_examples = f"""
        [예시 1: '체류자격 변경' 답변 추출 (다음 조건부 질문 2개 스킵)]
        question: "{question}"
        user_message: "E-7 자격으로 변경하고 싶습니다."
        AI: {{"status": "success", "filled_fields": {{"app_change_desired": "E-7"}}, "skip_next_n_questions": 2, "follow_up_question": null}}
        
        [예시 2: '체류자격 변경' 답변 추출 (다음 조건부 질문 2개 스킵)]
        question: "{question}"
        user_message: "F2 비자요"
        AI: {{"status": "success", "filled_fields": {{"app_change_desired": "F-2"}}, "skip_next_n_questions": 2, "follow_up_question": null}}
        """

    # --------------------------------------------------------------------
    # [신규 추가] 분기 1-2: '체류자격 부여' 희망 자격
    # (application_type에서 이 질문으로 넘어옴)
    # (이 질문에 답하면, 남은 조건부 질문 1개(app_other)를 스킵)
    # --------------------------------------------------------------------
    elif field_id == "app_grant_desired":
        specific_examples = f"""
        [예시 1: '체류자격 부여' 답변 추출 (다음 조건부 질문 1개 스킵)]
        question: "{question}"
        user_message: "F-2 비자를 받고 싶어요."
        AI: {{"status": "success", "filled_fields": {{"app_grant_desired": "F-2"}}, "skip_next_n_questions": 1, "follow_up_question": null}}
        """

    # --------------------------------------------------------------------
    # [신규 추가] 분기 1-3: '체류자격외 활동' 내용
    # (application_type에서 이 질문으로 넘어옴)
    # (이 질문은 마지막 조건부 질문이므로 스킵 없음)
    # --------------------------------------------------------------------
    elif field_id == "app_other_desired":
        specific_examples = f"""
        [예시 1: '체류자격외 활동' 답변 추출 (스킵 없음)]
        question: "{question}"
        user_message: "학교에서 조교로 일하고 싶습니다."
        AI: {{"status": "success", "filled_fields": {{"app_other_desired": "학교 조교 활동"}}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 2: '체류자격외 활동' 답변 추출 (스킵 없음)]
        question: "{question}"
        user_message: "유튜브 채널 운영"
        AI: {{"status": "success", "filled_fields": {{"app_other_desired": "유튜브 채널 운영"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """
        
    # [분기 2: 직업]
    elif field_id == "occupation_type":
        # ❗️ [중요] 시나리오 리스트(1단계)를 기준으로 건너뛸 질문 개수 계산
        # 예: '학생' 질문(3개), '근무자' 질문(4개), '근무처 변경' 질문(2개)
        student_q_count = 4
        worker_q_count = 8
        
        #print("start OT")
        # 1. '학생' 선택 시: '근무자' 필드를 비우고, '근무자' 질문(6개) 스킵
        student_example_fields = {
            "current_workspace": "", 
            "cur_business_regis_num": "", 
            "new_workplace": "", 
            "new_business_regis_num": "",
            "occupation": "학생",
            "annual_income": ""
        }
        
        worker_fields_to_skip = {
            "current_workspace": "", "cur_business_regis_num": "", "cur_phone": "",
            "new_workplace": "", "new_business_regis_num": "", "new_phone": "",
            "occupation": "학생", "annual_income": ""
        }
        
        student_fields_to_skip = {
            "non": False, "ele": False, "mid": False, "hi": False,
            "ac": False, "no_ac": False, "alt": False,
            "school_name": "", "school_phone": ""
        }
        
        # 3. '기타' 선택 시: '학생' + '근무자' 필드를 비우고, '학생'(3개) + '근무자'(6개) 질문 스킵
        other_example_fields = {**student_example_fields, **student_fields_to_skip}
        other_example_json = json.dumps({
            "status": "success",
            "filled_fields": other_example_fields,
            "skip_next_n_questions": student_q_count + worker_q_count,
            "follow_up_question": None
        })
        
        specific_examples = f"""
        [예시 1: '학생' 선택 (다음 질문으로 이동, {len(student_example_fields)}개 필드 비움)]
        question: "{question}"
        user_message: "저 학생이에요"
        AI: {{"status": "success", "filled_fields": {json.dumps(worker_fields_to_skip, ensure_ascii=False)}, "skip_next_n_questions": 0, "follow_up_question": null}}

        [예시 2: '근무자' 선택 (학생 관련 질문 {student_q_count}개 스킵 + {len(student_fields_to_skip)}개 필드 비움)]
        question: "{question}"
        user_message: "회사 다니고 있어요"
        AI: {{"status": "success", "filled_fields": {json.dumps(student_fields_to_skip, ensure_ascii=False)}, "skip_next_n_questions": 0, "follow_up_question": null}}
        
        [예시 3: '기타' 선택 (학생+근무자 질문 {student_q_count + worker_q_count}개 스킵 + {len(other_example_fields)}개 필드 비움)]
        question: "{question}"
        user_message: "둘 다 아닙니다."
        AI: {{"status": "success", "filled_fields": {json.dumps({**student_fields_to_skip, **worker_fields_to_skip}, ensure_ascii=False)}, "skip_next_n_questions": {student_q_count + worker_q_count}, "follow_up_question": null}}
        """
        print("slelect occpu_type")
        
    elif field_id == "school_status":
        specific_examples = f"""
        [템플릿 변수명 목록]
        "non", "ele", "mid", "hi"

        [예시 1: '초' 선택]
        question: "{question}"
        user_message: "초등학교요"
        AI: {{"status": "success", "filled_fields": {{"non": false, "ele": true, "mid": false, "hi": false}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        
        [예시 2: '미취학' 선택]
        question: "{question}"
        user_message: "미취학입니다"
        AI: {{"status": "success", "filled_fields": {{"non": true, "ele": false, "mid": false, "hi": false, "ac": false, "no_ac": false, "alt": false, "school_name": "", "school_phone": ""}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """
        print("select school status")
        
    # ❗️ [신규 추가] 분기 2-2: 학교 종류
    elif field_id == "school_type":
        specific_examples = f"""
        [템플릿 변수명 목록]
        "ac", "no_ac", "alt"

        [예시 1: '교육청 인가' 선택]
        question: "{question}"
        user_message: "교육청 인가받은 곳이에요"
        AI: {{"status": "success", "filled_fields": {{"ac": true, "no_ac": false, "alt": false}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        
        [예시 2: '대안학교' 선택]
        question: "{question}"
        user_message: "대안학교"
        AI: {{"status": "success", "filled_fields": {{"ac": false, "no_ac": false, "alt": true}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """
        print("select school type")
        
    elif field_id == "school_name":
        specific_examples = f"""
        [예시 1: 학교 이름 입력]
        question: "{question}"
        user_message: "대구고등학교 입니다."
        AI: {{"status": "success", "filled_fields": {{"{field_id}": "대구고등학교"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """
    
    elif field_id == "school_phone":
        specific_examples = f"""
        [예시 1: 학교 전화번호 입력]
        question: "{question}"
        user_message: "02-123-4567 입니다."
        AI: {{"status": "success", "filled_fields": {{"{field_id}": "02-123-4567"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """

    # [기본 텍스트] 예시
    else: 
        specific_examples = f"""
        [예시 1: 일반 텍스트 추출]
        question: "{question}"
        user_message: "성은 PARK입니다."
        AI: {{"status": "success", "filled_fields": {{"{field_id}": "PARK"}}, "skip_next_n_questions": 0, "follow_up_question": null}}
        """

    # --- (이하 API 호출 로직은 working_ai.py와 동일) ---
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
        
        ai_response_str = response.choices[0].message.content
        ai_response_json = json.loads(ai_response_str)
        return ai_response_json
    except Exception as e:
        print(f"OpenAI (get_smart_extraction - foreign_app) API call failed: {e}")
        # 실패 시 롤백 (단순 값 저장)
        return {
            "status": "success", 
            "filled_fields": {field_id: user_message}, 
            "skip_next_n_questions": 0,
            "follow_up_question": None
        }

# --- 3. 통합신청서 전용 "다음 질문 찾기" 로직 ---
# (이 로직은 AI가 스킵을 담당하므로, 'working_ai.py'와 거의 동일하게 유지)
def find_next_question(
    current_content: Dict[str, Any]
) -> Tuple[Optional[Dict], int]:
    """
    '통합신청서' 시나리오를 기반으로 다음에 물어볼 질문(item)과 인덱스(index)를 반환합니다.
    """
    scenario = CONTRACT_SCENARIO
    
    current_question_item: Optional[Dict] = None
    current_question_index = -1 

    for i, item in enumerate(scenario):
        field_id = item["field_id"]
        
        # ==========================
        # (1) 생년월일 특수 처리
        # ==========================
        if field_id == "birth":
            if all(k in current_content for k in ["birth_yyyy", "birth_mm", "birth_dd"]):
                continue  # 세 값 모두 있으면 '채워짐'으로 간주
            
        # ==========================
        # (2) 기본 필드 확인
        # ==========================
        if field_id in current_content:
            continue
        
        # ==========================
        # (3) 체크박스형 항목들 처리
        # ==========================
        if field_id == "sex" and ("sex_m_check" in current_content or "sex_f_check" in current_content):
            continue
        if field_id == "application_type":
            app_keys = ["fore_resident_regis", "re_regis_card", "ex_sojo_peri", "chg_stus_sojo", "grant_sojourm", "engage_act_not_sojo",
                        "chg_add_wrkplc", "reen_permit", "alt_residence", "chg_registration"]
            if any(key in current_content for key in app_keys):
                continue
        if field_id == "occupation_type":
            if ("school_name" in current_content or 
                "current_workspace" in current_content or
                field_id in current_content):
                continue
        if field_id == "school_status":
            status_keys = ["non", "ele", "mid", "hi"]
            if any(key in current_content for key in status_keys):
                continue

        if field_id == "school_type":
            type_keys = ["ac", "no_ac", "alt"]
            if any(key in current_content for key in type_keys):
                continue
            
        # ==========================
        # (4) 다음 질문 확정
        # ==========================
        current_question_index = i
        current_question_item = item
        break
    
    # 모든 질문을 다 채운 경우
    if current_question_item is None:
        current_question_index = len(scenario)

    return current_question_item, current_question_index

def validate_fields(new_fields: Dict[str, Any]) -> Optional[str]:
    """
    AI가 추출한 데이터(new_fields)의 유효성을 검사합니다.
    문제가 있으면 에러 메시지(str)를 반환하고, 문제가 없으면 None을 반환합니다.
    """
    
    # 1. 영문 성/이름 검증 (surname, given_names)
    # -> 영문 대소문자와 공백만 허용
    for field in ["surname", "given_names"]:
        if field in new_fields:
            value = new_fields[field]
            if not re.match(r"^[a-zA-Z\s]+$", str(value)):
                return "성명(Surname/Given Names)은 반드시 '영문'으로 입력해야 합니다. (한글 불가)"

    # 2. 생년월일 검증 (birth_yyyy, birth_mm, birth_dd)
    # -> 숫자 범위 확인
    if "birth_yyyy" in new_fields:
        y = int(new_fields["birth_yyyy"])
        if not (1900 <= y <= datetime.date.today().year):
            return "태어난 연도가 올바르지 않습니다."
            
    if "birth_mm" in new_fields:
        m = int(new_fields["birth_mm"])
        if not (1 <= m <= 12):
            return "월(Month)은 1~12 사이의 숫자여야 합니다."
            
    if "birth_dd" in new_fields:
        d = int(new_fields["birth_dd"])
        if not (1 <= d <= 31):
            return "일(Day)은 1~31 사이의 숫자여야 합니다."

    # 3. 외국인등록번호 검증 (foreign_num)
    # -> 13자리 숫자 (하이픈 포함 여부 고려)
    if "foreign_num" in new_fields:
        # 숫자만 추출
        num_only = re.sub(r"[^0-9]", "", str(new_fields["foreign_num"]))
        if len(num_only) != 13:
            return "외국인등록번호는 13자리 숫자여야 합니다."

    # 4. 전화번호 검증 (tele_num, phone_num)
    # -> 숫자와 하이픈만 허용, 최소 길이 확인
    for field in ["tele_num", "phone_num"]:
        if field in new_fields:
            value = new_fields[field]
            # 간단한 정규식: 숫자, 하이픈, 공백, 괄호 허용
            if not re.match(r"^[0-9\-\s\(\)]+$", str(value)):
                return "전화번호 형식이 올바르지 않습니다."
            if len(re.sub(r"[^0-9]", "", str(value))) < 8: # 숫자가 너무 적으면 의심
                return "전화번호가 너무 짧습니다. 다시 확인해주세요."
                
    # 5. 이메일 검증 (email)
    if "email" in new_fields:
        value = new_fields["email"]
        # 기본적인 이메일 정규식
        if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", str(value)):
            return "이메일 형식이 올바르지 않습니다. (예: user@example.com)"

    # 검증 통과
    return None

async def process_message(
    db: AsyncSession,
    contract,
    message: str
) -> schemas.ChatResponse:

    content = contract.content or {}
    
    if "apply_date" not in content:
        today = datetime.date.today()
        content["apply_date"] = today.strftime("%Y-%m-%d")
    
    new_chat_history = contract.chat_history.copy() if isinstance(contract.chat_history, list) else []

    # ✅ 1) 다음 질문 찾기
    current_item, _ = find_next_question(content)
    current_bot_question = current_item["question"] if current_item else None    
    current_field_id = current_item["field_id"] if current_item else None # (나중에 사용)
    
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

    # -----------------------------------------------------------
    # ✅ [수정 1] 공통 채팅 기록 저장 (무조건 저장)
    # -----------------------------------------------------------
    # 사용자가 말을 했으므로, [봇의 질문] -> [사용자의 말]을 기록에 남깁니다.
    if current_bot_question:
        new_chat_history.append({"sender": "bot", "message": current_bot_question})
    
    new_chat_history.append({"sender": "user", "message": message})
    # -----------------------------------------------------------
    
    # -----------------------------------------------------------
    # ✅ [핵심 수정] 3) AI 추출 및 의도 파악 실행
    # -----------------------------------------------------------
    
    # (A) 폼 작성이 완료된 경우 -> 무조건 RAG 모드로 진입
    if current_item is None:
        ai_result = {"status": "rag_required"} # 강제로 RAG 상태 설정
        
    # (B) 폼 작성 중인 경우 -> AI에게 추출 시도
    else:
        ai_result = await get_smart_extraction(
            client,
            current_field_id, # ❗️ 위에서 안전하게 가져온 변수 사용
            message,
            current_bot_question
        )
        
        '''
    # 3) AI 추출 및 의도 파악 실행
    ai_result = await get_smart_extraction(
        client,
        current_item["field_id"],
        message,
        current_item["question"]
    )
'''

    # -----------------------------------------------------------
    # ✅ [수정 2] RAG(법률 질문) 처리
    # -----------------------------------------------------------
    if ai_result.get("status") == "rag_required":
        tips, score = await find_top_relevant_tips(message)
        rag_answer = await get_rag_response(message, tips)
        
        # RAG 답변을 기록에 추가
        new_chat_history.append({"sender": "bot", "message": rag_answer})

        # ❗️ [수정] 완료 여부에 따라 후속 멘트 다르게 처리
        if current_item:
            follow = f"\n\n(답변이 되셨나요? 이어서 진행합니다.)\n{current_item['question']}"
            is_finished = False
        else:
            follow = "\n\n(추가로 궁금한 점이 있으신가요? 언제든 물어봐 주세요.)"
            is_finished = True # 이미 완료된 상태
            
        '''
        # RAG 답변 후, 원래 물어봤던 질문을 다시 이어서 붙임 (화면 표시용)
        follow = (
            f"\n\n(답변이 되셨나요? 이어서 진행합니다.)\n{current_item['question']}"
            if current_item else ""
        )
        '''
        
        return schemas.ChatResponse(
            reply=rag_answer + follow,
            updated_field=None,
            is_finished=False,
            full_contract_data=content,
            chat_history=new_chat_history
        )
    
    # -----------------------------------------------------------
    # 4) 정상적인 폼 답변 처리 (status == "success" or "clarify")
    # -----------------------------------------------------------
    
    
    # AI가 추출한 데이터 적용
    new_fields = ai_result.get("filled_fields", {})
    
    #--------------------추가--------------------
    # 데이터 세탁 (Sanitization)
    for k, v in new_fields.items():
        if isinstance(v, str): new_fields[k] = v.strip()
        
    validation_error = validate_fields(new_fields)
    if validation_error:
        error_reply = f"{validation_error}\n다시 입력해 주세요.\n\n(질문: {current_bot_question})"
        # 검증 실패 시: 에러 메시지를 봇이 말하게 하고, 저장은 하지 않음
        new_chat_history.append({"sender": "bot", "message": error_reply})
        
        return schemas.ChatResponse(
            reply=validation_error, # "영문으로 입력해주세요" 등의 메시지 반환
            updated_field=None,
            is_finished=False,
            full_contract_data=content, # 잘못된 데이터는 저장되지 않은 원본 반환
            chat_history=new_chat_history
        )
    
    content.update(new_fields)
    
    # (중요: skip_n 로직은 삭제됨 - filled_fields가 처리함)
    skip_n = ai_result.get("skip_next_n_questions", 0)
    for _ in range(skip_n):
        # ❗️ content가 이미 update된 상태에서 find_next_question을 호출
        _, idx = find_next_question(content) 
        if idx < len(CONTRACT_SCENARIO):
            # 다음 질문을 "__SKIPPED__"로 강제 마킹하여 채움
            content[CONTRACT_SCENARIO[idx]["field_id"]] = ""
    
    # 재질문(clarify) 처리
    if ai_result.get("status") == "clarify":
        follow_up_q = ai_result["follow_up_question"]
        
        # 재질문 내용도 기록에 추가
        new_chat_history.append({"sender": "bot", "message": follow_up_q})
        
        return schemas.ChatResponse(
            reply=follow_up_q,
            updated_field=None,
            is_finished=False,
            full_contract_data=content,
            chat_history=new_chat_history
        )
     
    # ✅ 다음 질문 찾기
    next_item, _ = find_next_question(content)

    # new_fields 에 값이 있을 때, UpdatedField 리스트로 변환
    def make_updated_field_list(fields: Dict[str, Any]) -> Optional[List[schemas.UpdatedField]]:
        if not fields:
            return None
        lst: List[schemas.UpdatedField] = []
        for k, v in fields.items():
            # schemas.UpdatedField 모델을 직접 생성해서 타입 안전성 확보
            lst.append(schemas.UpdatedField(field_id=k, value=v))
        return lst

    updated_field_list = make_updated_field_list(new_fields)

    if next_item:
        return schemas.ChatResponse(
            reply=next_item["question"],
            updated_field=updated_field_list,   # 이제 항상 리스트 또는 None
            is_finished=False,
            full_contract_data=content,
            chat_history=new_chat_history
        )

    else:
        # 모든 항목 작성 완료 상태
        return schemas.ChatResponse(
            reply="모든 항목이 작성되었습니다.",
            updated_field=updated_field_list,   # 마지막에 업데이트된 필드(있으면 리스트), 없으면 None
            is_finished=True,
            full_contract_data=content,
            chat_history=new_chat_history
        )


# -----------------------------------------------------------
# ✅ 5. DOCX 렌더링
# -----------------------------------------------------------
TEMPLATE_FILE = "foreign.docx"

async def render_docx(contract):
    """통합신청서 템플릿(.docx)을 렌더링해 DocxTemplate 객체로 반환."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(current_dir, "..", "..", "templates", TEMPLATE_FILE)
    
    # 경로 디버깅용 (서버 콘솔에 실제 경로 출력)
    print(f"📂 Using template path: {template_path}")

    # 파일 존재 여부 검증
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"❌ Template not found at {template_path}")

    doc = DocxTemplate(template_path)
    context = contract.content or {}
    '''clean_context = {
        key: value 
        for key, value in context.items() 
        if value != ""
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