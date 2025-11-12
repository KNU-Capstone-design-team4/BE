# API가 주고받을 데이터의 모양을 Pydantic 모델로 정의
# app/schemas.py
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID
from typing import List

# =================================================================
#                         사용자 (User)
# =================================================================

# 회원가입 요청 시 사용
class UserSignUp(BaseModel):
    """
    Supabase auth.sign_up()에 필요한 사용자 정보를 정의합니다.
    """
    email: EmailStr
    password: str
    username: str 
    name: Optional[str] = None  # Supabase user_metadata에 저장될 이름
    phone: Optional[str] = None # Supabase user_metadata에 저장될 전화번호

# 로그인 요청 시 사용
class UserLogin(BaseModel):
    """
    Supabase auth.sign_in_with_password()에 필요한 자격 증명을 정의합니다.
    """
    email: str
    password: str




## 2. 인증 응답 스키마 (서버 -> 클라이언트)

class TokenResponse(BaseModel):
    """
    로그인 성공 시 API 응답 본문의 형식을 정의합니다.
    (토큰은 HTTPOnly 쿠키로도 전달되지만, API 응답에도 포함될 수 있음)
    """
    access_token: str
    token_type: str = "bearer"


# =================================================================
#                         계약서 (Contract)
# =================================================================

# 새 계약서 생성 시 받을 데이터 (Request)
class ContractCreate(BaseModel):
    contract_type: str

# 내 계약서 목록 조회 시 보낼 각 계약서의 기본 정보 (Response)
class ContractInfo(BaseModel):
    id: UUID
    contract_type: str
    updated_at: datetime

    class Config:
        from_attributes = True
        
# 특정 계약서 상세 조회 시 보낼 전체 정보 (Response)
class ContractDetail(BaseModel):
    id: UUID
    contract_type: str
    content: Optional[Dict[str, Any]] = None # JSON 필드는 Dict로 표현
    status: str
    updated_at: datetime
    owner_id: UUID
    
 # ❗️ [추가] 챗봇의 현재 상태
    next_question: Optional[str] = None  # (예: "고용주 성함은?", 완료 시 null)

    # ✅ [추가] 프론트에서 미리보기용 HTML 템플릿
    templateHtml: Optional[str] = None   # HTML 문서 전체를 문자열로 반환

    # ✅ [추가] 대화 히스토리 (선택적으로 포함 가능)
    chatHistory: Optional[List[Dict[str, Any]]] = None
    
    class Config:
        from_attributes = True


# =================================================================
#                         챗봇 (Chat)
# =================================================================

# 챗봇에게 보낼 메시지 (Request)
class ChatRequest(BaseModel):
    message: str

# 챗봇이 계약서 필드를 업데이트했을 때의 정보
class UpdatedField(BaseModel):
    field_id: str # 프론트엔드와 약속된 필드의 고유 ID
    value: Any    # 해당 필드에 업데이트된 값

# 챗봇의 응답 (Response)
class ChatResponse(BaseModel):
    reply: str
    updated_field: Optional[List[UpdatedField]] = None
    is_finished: bool
    full_contract_data: Optional[Dict[str, Any]] = None
    chat_history: Optional[List[Dict[str, Any]]] = None
