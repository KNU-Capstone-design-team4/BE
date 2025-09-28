# API가 주고받을 데이터의 모양을 Pydantic 모델로 정의
# app/schemas.py
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, Dict, Any, List

# =================================================================
#                         사용자 (User)
# =================================================================

# 회원가입 시 받을 데이터 (Request)
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

# 로그인 시 받을 데이터 (Request)
class UserLogin(BaseModel):
    email: EmailStr
    password: str

# 클라이언트로 보낼 사용자 정보 (Response) - 비밀번호 제외
class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    created_at: datetime

    class Config:
        from_attributes = True


# =================================================================
#                         인증 (Token)
# =================================================================

# 로그인 성공 시 보낼 JWT 토큰 정보 (Response)
class Token(BaseModel):
    access_token: str
    token_type: str


# =================================================================
#                         계약서 (Contract)
# =================================================================

# 새 계약서 생성 시 받을 데이터 (Request)
class ContractCreate(BaseModel):
    contract_type: str

# 내 계약서 목록 조회 시 보낼 각 계약서의 기본 정보 (Response)
class ContractInfo(BaseModel):
    id: int
    contract_type: str
    updated_at: datetime

    class Config:
        from_attributes = True
        
# 특정 계약서 상세 조회 시 보낼 전체 정보 (Response)
class ContractDetail(BaseModel):
    id: int
    contract_type: str
    content: Optional[Dict[str, Any]] = None # JSON 필드는 Dict로 표현
    status: str
    updated_at: datetime
    owner_id: int

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
    updated_field: Optional[UpdatedField] = None
    is_finished: bool
    full_contract_data: Optional[Dict[str, Any]] = None

