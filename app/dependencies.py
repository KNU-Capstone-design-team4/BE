from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from . import crud, models
from .database import get_db
# security.py에서 JWT 관련 설정을 모두 가져옵니다.
from .security import ALGORITHM, SECRET_KEY

# FastAPI가 요청 헤더에서 'Authorization: Bearer [토큰]'을 찾아 토큰을 추출하게 합니다.
# tokenUrl은 실제 로그인 API의 경로를 가리킵니다.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> models.User:
    """
    SQLAlchemy ORM을 위한 JWT 토큰 검증 및 사용자 반환 의존성.
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

async def verify_supabase_token(token: str = Depends(oauth2_scheme)):
    """
    Supabase 클라이언트를 위한 JWT 토큰 검증 의존성.
    """
    try:
        # Supabase 클라이언트를 사용하여 토큰으로부터 사용자 정보를 가져옵니다.
        user_response = supabase.auth.get_user(token)
        return user_response.user.dict()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Supabase authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

