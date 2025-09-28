import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

# .env 파일에서 환경 변수를 로드합니다.
load_dotenv()

# .env 파일에서 DATABASE_URL 값을 가져옵니다.
SUPABASE_URL = os.getenv("DATABASE_URL")

# DATABASE_URL이 제대로 로드되었는지 확인합니다.
if not SUPABASE_URL:
    raise ValueError("DATABASE_URL 환경 변수를 찾을 수 없습니다. .env 파일을 확인해주세요.")

# asyncpg 드라이버를 사용하도록 URL을 수정합니다.
DATABASE_URL = SUPABASE_URL.replace("postgresql://", "postgresql+asyncpg://")


engine = create_async_engine(DATABASE_URL)
async_session = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()

# DB 세션 의존성 주입 함수
async def get_db():
    async with async_session() as session:
        yield session

