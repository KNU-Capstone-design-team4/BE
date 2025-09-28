# 데이터베이스 테이블의 구조를 python 클래스로 정의
# app/models.py
from sqlalchemy import Column, Integer, String, ForeignKey, JSON, TIMESTAMP
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base

class User(Base):
    """
    사용자 정보를 저장하는 테이블 모델
    - SQLAlchemy ORM이 이 클래스를 보고 'users' 테이블을 관리합니다.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    # TIMESTAMPTZ를 TIMESTAMP(timezone=True)로 수정
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    # User와 Contract 간의 관계 설정
    contracts = relationship("Contract", back_populates="owner")


class Contract(Base):
    """
    생성된 계약서 정보를 저장하는 테이블 모델
    - SQLAlchemy ORM이 이 클래스를 보고 'contracts' 테이블을 관리합니다.
    """
    __tablename__ = "contracts"

    id = Column(Integer, primary_key=True, index=True)
    contract_type = Column(String, index=True, nullable=False)
    content = Column(JSON, nullable=True)
    status = Column(String, default="in_progress")
    # TIMESTAMPTZ를 TIMESTAMP(timezone=True)로 수정
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # users 테이블의 id를 참조하는 외래 키(Foreign Key) 설정
    owner_id = Column(Integer, ForeignKey("users.id"))
    
    # Contract와 User 간의 관계 설정
    owner = relationship("User", back_populates="contracts")

