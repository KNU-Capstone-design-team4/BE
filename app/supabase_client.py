import os
from supabase import create_client, Client
from dotenv import load_dotenv

# .env 파일에서 환경 변수를 로드합니다. (로컬 개발 환경용)
# 배포 환경에서는 시스템 환경 변수를 사용해야 합니다.
load_dotenv()

# 환경 변수에서 Supabase URL과 Key를 가져옵니다.
# 반드시 여러분의 실제 키와 URL로 대체하거나 .env 파일에 설정해야 합니다.
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") # 또는 'SUPABASE_ANON_KEY'

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL 또는 SUPABASE_KEY 환경 변수가 설정되지 않았습니다.")

# Supabase 클라이언트 초기화
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("Supabase 클라이언트가 성공적으로 초기화되었습니다.")
except Exception as e:
    print(f"Supabase 클라이언트 초기화 중 오류 발생: {e}")
    # 프로덕션에서는 이 예외를 처리하고 애플리케이션 시작을 중단해야 합니다.
    supabase = None