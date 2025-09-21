from fastapi import FastAPI, HTTPException, status, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import Column, Integer, String, select
from sqlalchemy.orm import declarative_base
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone

# --- 데이터베이스 설정 (register.py와 동일하게 설정) ---
DATABASE_URL = "postgresql+asyncpg://lawbot_user:lawbotuser@localhost:5432/lawbot_db"

engine = create_async_engine(DATABASE_URL)
async_session = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()

# --- 데이터베이스 테이블 모델 정의 (register.py와 동일) ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)

# --- JWT 설정 ---
SECRET_KEY = "your-secret-key"  # 실제 프로젝트에서는 .env 파일 등으로 관리해야 합니다.
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# --- 데이터 모양(스키마) 정의 ---
# 로그인 요청 시 받을 데이터 모양
class UserLogin(BaseModel):
    email: EmailStr
    password: str

# 로그인 성공 시 보내줄 토큰 모양
class Token(BaseModel):
    access_token: str
    token_type: str

# --- 비밀번호 암호화/검증 설정 (register.py와 동일) ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- FastAPI 앱 생성 ---
app = FastAPI()

# --- DB 세션 의존성 주입 (register.py와 동일) ---
async def get_db():
    async with async_session() as session:
        yield session

# --- 핵심 함수 ---
# 1. 비밀번호 검증 함수
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# 2. JWT 액세스 토큰 생성 함수
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# --- 로그인 API 엔드포인트 구현 ---
@app.post("/api/users/login", response_model=Token)
async def login_for_access_token(form_data: UserLogin, db: AsyncSession = Depends(get_db)):
    # 1. DB에서 이메일로 사용자 조회
    result = await db.execute(select(User).filter(User.email == form_data.email))
    user = result.scalar_one_or_none()
    
    # 2. 사용자가 없거나, 비밀번호가 틀린 경우 오류 발생
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 정확하지 않습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # 3. JWT 토큰 생성
    access_token = create_access_token(
        data={"sub": user.email}
    )
    
    # 4. 토큰 반환
    return {"access_token": access_token, "token_type": "bearer"}