from fastapi import Depends, HTTPException, status
# ❗️ 변경점: OAuth2PasswordBearer 대신 HTTPBearer와 HTTPAuthorizationCredentials를 import
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from . import crud, models
from .database import get_db, supabase_client  # supabase_client도 import합니다
# security.py에서 JWT 관련 설정을 모두 가져옵니다.
from .security import ALGORITHM, SECRET_KEY

# ❗️ 변경점: oauth2_scheme 대신 bearer_scheme을 사용합니다.
bearer_scheme = HTTPBearer()

'''async def verify_supabase_token(
    # ❗️ 변경점: 이 함수도 일관성을 위해 bearer_scheme을 사용하도록 수정
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
):
    """
    Supabase 클라이언트를 위한 JWT 토큰 검증 의존성.
    """
    # ❗️ 추가점: credentials 객체에서 실제 토큰 문자열을 추출합니다.
    token = credentials.credentials
    try:
        # Supabase 클라이언트를 사용하여 토큰으로부터 사용자 정보를 가져옵니다.
        user_response = supabase_client.auth.get_user(token)
        # user_response.user가 None일 경우를 대비한 예외 처리 추가
        if not user_response.user:
            raise Exception("User not found for the provided token.")
        return user_response.user.dict()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Supabase authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )'''
# 인증(authorize)과정이 계속 실패해서 디버깅용으로 함수를 만듦
async def verify_supabase_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
):
    """
    Supabase 클라이언트를 위한 JWT 토큰 검증 의존성.
    """
    # --- 디버깅 코드 시작 ---
    print("=========================================================")
    print(">>> DEBUG: 'verify_supabase_token' 함수가 호출되었습니다.")
    # --- 디버깅 코드 끝 ---

    token = credentials.credentials

    # --- 디버깅 코드 시작 ---
    # 토큰이 너무 길기 때문에 앞 30자만 출력해봅니다.
    print(f">>> DEBUG: 서버가 받은 토큰 (앞 30자): {token[:30]}...")
    # --- 디버깅 코드 끝 ---
    try:
        user_response = supabase_client.auth.get_user(token)
        
        # --- 디버깅 코드 시작 ---
        print(f">>> DEBUG: Supabase 응답 성공! User: {user_response.user.email if user_response.user else '없음'}")
        # --- 디버깅 코드 끝 ---

        if not user_response.user:
            raise Exception("User not found for the provided token.")
        return user_response.user.dict()
    except Exception as e:
        # --- 디버깅 코드 시작 ---
        print(f">>> DEBUG: 'verify_supabase_token' 함수에서 예외 발생: {e}")
        print("=========================================================")
        # --- 디버깅 코드 끝 ---
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Supabase authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

