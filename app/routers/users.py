from fastapi import APIRouter, status, HTTPException, Depends
from starlette.responses import JSONResponse
from app.supabase_client import supabase

# v2 SDK 기준 import
from postgrest import APIError as PostgrestAPIError
from gotrue.errors import AuthApiError

from ..dependencies import verify_supabase_token

from app.schemas import UserSignUp
from app.schemas import UserLogin

import traceback

from app.database import supabase_client, supabase_admin

#app = APIRouter(prefix="/user")

#@app.post("/signup")

# FastAPI() 대신 APIRouter()를 사용합니다.
router = APIRouter(
    prefix="/api/users", # 이 파일의 모든 API 주소는 /api/users로 시작합니다.
    tags=["users"]      # API 문서에 'users' 그룹으로 표시됩니다.
)

# @app.post 대신 @router.post를 사용합니다.
@router.post("/signup", status_code=status.HTTP_200_OK)

async def signup(new_user: UserSignUp):
    try:
        # 1. Supabase Auth에 사용자 생성
        res = supabase.auth.sign_up({
            "email": new_user.email,
            "password": new_user.password,
        })

        print("=== SIGNUP RESPONSE ===")
        print("RES:", res)
        print("USER:", getattr(res, "user", None))

        if not res.user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="User creation failed, no user returned."
            )

        user_id = res.user.id  # auth.users.id (UUID)

        # 2. profiles 테이블에 추가 정보 삽입 (결과 변수 안 받음)
        supabase.table("profiles").insert({
            "id": user_id,
            "username": new_user.username,
            "name": new_user.name,
            "phone": new_user.phone
        }).execute()

        print("=== PROFILE INSERT RESPONSE ===")
        print("Profile inserted successfully (no result captured).")

        # 3. 최종 응답
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": f"Signup successful. User ID: {user_id}"}
        )

    except AuthApiError as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=400,
            detail=f"Authentication error: {e.message}"
        )

    except PostgrestAPIError as e:
        traceback.print_exc()
        if "duplicate key value" in str(e):
            raise HTTPException(
                status_code=409,
                detail="Username already exists. Please choose a different one."
            )
        raise HTTPException(
            status_code=500,
            detail=f"Database error during profile creation: {str(e)}"
        )

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )
    
@router.post("/login")
async def login(user_credentials: UserLogin):
    """
    이메일과 비밀번호로 Supabase에 로그인하고, 세션 정보를 반환합니다.
    """
    try:
        # 1. Supabase GoTrue 인증 시스템에 로그인 요청을 보냄
        res = supabase.auth.sign_in_with_password({
            "email": user_credentials.email,
            "password": user_credentials.password,
        })

        #2. 인증 성공 후 세션과 사용자가 모두 반환되었는지 확인함.
        if not res.user or not res.session:
             raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Login failed: Invalid credentials or session not established."
            )

        # 3. 로그인 성공 시, 클라이언트에게 필요한 세션 정보를 반환함.
        # access_token은 이후의 모든 인증된 API 요청에 사용됨
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "Login successful",
                "user_id": res.user.id,
                "access_token": res.session.access_token,
                "refresh_token": res.session.refresh_token,
                "expires_in": res.session.expires_in,
                "token_type": res.session.token_type,
            }
        )

    except AuthApiError as e:
        # 인증 오류 처리 (예: "Invalid login credentials" 등)
        print(f"AuthApiError during login: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication error: {e.message}"
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(current_user: dict = Depends(verify_supabase_token)):
    """
    유효한 토큰을 검증하여 현재 사용자의 세션을 종료하고 로그아웃을 처리합니다.
    """
    try:
        # 1. 토큰 검증 완료
        # Depends(verify_supabase_token) 덕분에, 이 함수가 실행되는 것은
        # 이미 요청 헤더의 토큰이 유효하다는 것이 보장됨을 의미합니다.

        # 2. Supabase GoTrue 시스템에 로그아웃 요청을 보냄
        supabase.auth.sign_out()

        # 3. 로그아웃 성공 응답
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "Logout successful. All user sessions have been terminated globally."}
        )

    except AuthApiError as e:
        # Supabase 서버에서 발생하는 인증 관련 오류 처리
        traceback.print_exc()
        # 토큰 검증은 통과했지만, 서버 측 문제로 로그아웃이 실패했을 경우 500 에러 반환
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication server error during signout: {e.message}"
        )
        
    except Exception as e:
        # 예상치 못한 기타 오류 처리
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected internal error occurred during logout: {str(e)}"
        )