import os
from dotenv import load_dotenv
from supabase import create_client, Client
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

# .env 파일에서 환경 변수를 로드합니다.
load_dotenv()

# =================================================================
#   1. Supabase 공식 클라이언트 설정 (주로 인증용)
# =================================================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Supabase 클라이언트용 환경 변수가 모두 있는지 확인합니다.
if not all([SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_ROLE_KEY]):
    raise ValueError("Supabase 관련 환경 변수가 모두 설정되지 않았습니다. .env 파일을 확인해주세요.")

# 일반 클라이언트 (사용자 인증 등 RLS 정책 적용)
#supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 관리자 클라이언트 (RLS 정책 우회, 내부 로직용)
#supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)          # 일반 클라이언트
supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
# =================================================================
#   2. SQLAlchemy 엔진 설정 (주로 데이터 작업용)
# =================================================================
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

# SQLAlchemy용 환경 변수가 있는지 확인합니다.
if not SQLALCHEMY_DATABASE_URL:
    raise ValueError("DATABASE_URL 환경 변수를 찾을 수 없습니다. .env 파일을 확인해주세요.")

# asyncpg 드라이버를 사용하도록 URL을 수정합니다.
if SQLALCHEMY_DATABASE_URL.startswith("postgresql://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(SQLALCHEMY_DATABASE_URL)
async_session = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()


# =================================================================
#   3. DB 세션 의존성 주입 함수 (SQLAlchemy용)
# =================================================================
async def get_db():
    """
    SQLAlchemy 비동기 세션을 생성하여 API 경로에 주입하는 의존성 함수입니다.
    """
    async with async_session() as session:
        yield session

