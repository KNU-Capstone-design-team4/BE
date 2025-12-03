# 모든 라우터를 모아 최종 FastAPI 앱을 만듬
# app/main.py
from fastapi import FastAPI, Depends, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base
from .routers import users, contracts
from contextlib import asynccontextmanager

# ❗️ Lifespan 컨텍스트 매니저 정의
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 앱 시작 시 실행될 코드
    print("INFO:     Application startup. Initializing database connection.")
    # 이 부분에 특별한 시작 로직이 없다면 비워두어도 됩니다.
    # 연결은 첫 요청 시 자동으로 생성됩니다.
    
    yield  # 이 지점에서 애플리케이션이 실행됩니다.
    
    # 앱 종료 시 실행될 코드
    print("INFO:     Application shutdown. Disposing of the engine.")
    await engine.dispose()


# FastAPI 앱을 생성할 때 lifespan을 연결합니다.
app = FastAPI(lifespan=lifespan)

# FastAPI 애플리케이션 생성
'''app = FastAPI(
    title="LawBot API",
    description="AI를 활용한 표준계약서 작성 보조 서비스 API",
    version="0.1.0"
)'''

# CORS 미들웨어 설정
# 프론트엔드 주소 (예: http://localhost:3000) 에서 오는 요청을 허용합니다.
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://knu-capstone-1.vercel.app",
    "https://knucapstone1.vercel.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # 모든 HTTP 메소드 허용
    allow_headers=["*"], # 모든 HTTP 헤더 허용
)


'''# 서버 시작 시 DB 테이블 자동 생성
@app.on_event("startup")
async def startup():
    """
    애플리케이션이 시작될 때 한 번 실행됩니다.
    데이터베이스에 필요한 모든 테이블을 생성합니다.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.on_event("shutdown")
async def shutdown():
    """
    애플리케이션이 종료될 때 SQLAlchemy 엔진의 연결을 모두 닫습니다.
    """
    print("INFO:     Shutting down application. Disposing of the engine.")
    await engine.dispose()'''

# 각 기능별 라우터를 앱에 포함
app.include_router(users.router)
app.include_router(contracts.router)

@app.get("/")
def read_root():
    """
    루트 경로, 서버가 정상적으로 실행 중인지 확인하는 용도입니다.
    """
    return {"message": "Welcome to LawBot API"}

