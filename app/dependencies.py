import os
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone

from . import crud, models
from .database import get_db

# .env 파일에서 환경 변수를 로드합니다.
load_dotenv()

# =================================================================
#                         비밀번호 처리
# =================================================================

# 비밀번호 암호화에 사용할 알고리즘을 설정합니다.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """입력된 비밀번호와 해시된 비밀번호를 비교합니다."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """비밀번호를 해시하여 반환합니다."""
    return pwd_context.hash(password)


# =================================================================
#                         JWT 인증
# =================================================================

# .env 파일에서 JWT 관련 설정을 가져옵니다.
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# FastAPI가 요청 헤더에서 'Authorization: Bearer [토큰]'을 찾아 토큰을 추출하게 합니다.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/login")

def create_access_token(data: dict) -> str:
    """JWT 액세스 토큰을 생성합니다."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(
    token: str = Depends(oauth2_scheme), 
    db: AsyncSession = Depends(get_db)
) -> models.User:
    """
    JWT 토큰을 검증하고, 유효한 경우 해당 사용자 정보를 반환하는 의존성 함수입니다.
    이 함수를 필요로 하는 모든 API는 자동으로 로그인 인증을 거치게 됩니다.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # 토큰을 해독하여 payload를 얻습니다.
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # payload에서 이메일(subject)을 추출합니다.
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        # 토큰이 유효하지 않으면 예외를 발생시킵니다.
        raise credentials_exception
    
    # 이메일로 DB에서 사용자를 찾습니다.
    user = await crud.get_user_by_email(db, email=email)
    
    if user is None:
        # 사용자가 존재하지 않으면 예외를 발생시킵니다.
        raise credentials_exception
    
    # 모든 검증을 통과하면 사용자 객체를 반환합니다.
    return user

# ▼▼▼▼▼▼▼▼▼▼ 테스트를 위한 임시 함수 ▼▼▼▼▼▼▼▼▼▼
async def get_test_user(db: AsyncSession = Depends(get_db)) -> models.User:
    """
    테스트용으로 항상 id=1인 사용자를 반환하는 가짜 인증 함수입니다.
    """
    user = await crud.get_user_by_id(db, user_id=1) # crud.py에 get_user_by_id 함수가 필요합니다.
    if not user:
        # 테스트용 유저가 DB에 없는 경우를 대비한 예외 처리
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test user with id=1 not found in the database."
        )
    return user
# ▲▲▲▲▲▲▲▲▲▲ 테스트를 위한 임시 함수 ▲▲▲▲▲▲▲▲▲▲