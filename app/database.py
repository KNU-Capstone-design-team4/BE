import os
from dotenv import load_dotenv
from supabase import create_client, Client
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from uuid import uuid4

# .env 파일에서 환경 변수를 로드합니다.
load_dotenv()

# =================================================================
#   1. Supabase 공식 클라이언트 설정 (주로 인증용)
# =================================================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ⭐️ 아래 두 줄의 print 코드를 추가해주세요. ⭐️
print("================= DEBUGGING .env VALUES =================")
print(f"[*] SUPABASE_URL loaded by App: {SUPABASE_URL}")
print(f"[*] SUPABASE_KEY loaded by App: {SUPABASE_KEY}")
print("=========================================================")


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


# 고유한 Prepared Statement 이름을 생성하는 함수
def get_unique_statement_name():
    # '__asyncpg_UUID_STRING__' 형태의 고유 이름 생성
    return f"__asyncpg_{uuid4().hex}__"


# SQLAlchemy 엔진은 한 번만 생성하며, 두 가지 해결책을 모두 적용해야 합니다.
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={
        "statement_cache_size": 0, # 캐시 비활성화
        "prepared_statement_name_func": get_unique_statement_name, # 고유 이름 부여 (Supabase에서 필수)
    },
    # Supabase 환경에서 충돌을 더 줄이려면 NullPool 사용을 고려할 수 있습니다.
    # poolclass=NullPool
)

'''
engine = create_async_engine(SQLALCHEMY_DATABASE_URL)
# connect_args를 추가하여 prepared statement 캐시를 비활성화합니다.
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"statement_cache_size": 0}
)''' #10월3일 수정 12:51수정내용 
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

