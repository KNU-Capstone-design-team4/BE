# app/models.py

from sqlalchemy import Column, String, ForeignKey, JSON, TIMESTAMP
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID  # ❗️ UUID 타입을 import
import uuid

from .database import Base

# 기존 User 모델은 삭제하고, Profile 모델을 새로 정의합니다.
class Profile(Base):
    """
    Supabase의 'profiles' 테이블과 매핑되는 모델.
    Supabase auth 사용자의 공개 프로필 정보를 저장합니다.
    """
    __tablename__ = "profiles"

    # Supabase auth.users.id와 동일한 UUID 타입을 사용합니다.
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String, unique=True, index=True)
    name = Column(String)
    phone = Column(String)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    # Profile과 Contract 간의 관계 설정
    contracts = relationship("Contract", back_populates="owner_profile")


class Contract(Base):
    """
    생성된 계약서 정보를 저장하는 테이블 모델
    """
    __tablename__ = "contracts"

    
    #id = Column(Integer, primary_key=True, index=True)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_type = Column(String, index=True, nullable=False)
    content = Column(JSON, nullable=True)
    status = Column(String, default="in_progress")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # ❗️ 외래 키(Foreign Key)가 'profiles.id'를 참조하도록 수정합니다.
    # ❗️ 타입도 반드시 UUID여야 합니다.
    owner_id = Column(UUID(as_uuid=True), ForeignKey("profiles.id"), nullable=False)
    
    # ❗️ 관계 설정의 이름과 대상을 'Profile' 모델에 맞게 수정합니다.
    owner_profile = relationship("Profile", back_populates="contracts")
    # ✅ [추가] 채팅 기록을 저장할 컬럼
    # 기본값으로 빈 리스트 '[]'를 저장하도록 설정합니다.
    chat_history = Column(JSON, nullable=False, default=[])
