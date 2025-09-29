import os
from dotenv import load_dotenv
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from jose import jwt

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
#                         JWT 설정
# =================================================================

# .env 파일에서 JWT 관련 설정을 가져옵니다.
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# SECRET_KEY가 .env 파일에 설정되었는지 확인합니다.
if not SECRET_KEY:
    raise ValueError("JWT_SECRET_KEY 환경 변수를 찾을 수 없습니다. .env 파일을 확인해주세요.")


def create_access_token(data: dict) -> str:
    """JWT 액세스 토큰을 생성합니다."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

