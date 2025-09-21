from fastapi import FastAPI, HTTPException, status, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base
from passlib.context import CryptContext
import asyncio

# --- 데이터베이스 설정 (비동기 방식) ---
DATABASE_URL = "postgresql+asyncpg://lawbot_user:lawbotuser@localhost:5432/lawbot_db"

engine = create_async_engine(DATABASE_URL)
async_session = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()

# --- 데이터베이스 테이블 모델 정의 ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)

# --- 데이터 모양(스키마) 정의 ---
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr

    class Config:
        from_attributes = True

# --- 비밀번호 암호화 설정 ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- FastAPI 앱 및 DB 테이블 생성 ---
app = FastAPI()

# 서버 시작 시 DB 테이블 자동 생성
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# --- DB 세션 의존성 주입 ---
async def get_db():
    async with async_session() as session:
        yield session

# --- 회원가입 API 엔드포인트 구현 (비동기 방식) ---
@app.post("/api/users/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    # 이메일 중복 확인
    from sqlalchemy import select
    result = await db.execute(select(User).filter(User.email == user_data.email))
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 사용 중인 이메일입니다.",
        )

    # 비밀번호 암호화
    hashed_password = pwd_context.hash(user_data.password)

    # 새로운 사용자 객체 생성
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_password,
    )

    # 데이터베이스에 추가 및 저장
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return new_user