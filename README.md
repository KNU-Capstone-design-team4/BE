# ⚖️ LawBot Backend Server

> **AI 기반 법률 문서 및 민원 서류 자동 작성 서비스 'LawBot'의 백엔드 레포지토리입니다.** > 사용자와의 채팅을 통해 필요한 정보를 추출하고, 복잡한 법률 서식을 자동으로 완성해줍니다.

<br/>

## 👥 팀원 소개 (Backend)

| 이름 | 역할 | 깃허브 |
| :---: | :---: | :---: |
| **박지영** | Backend Developer | [@GitHubID](https://github.com/) |
| **이영인** | Backend Developer | [@GitHubID](https://github.com/) |

<br/>

## 🛠 Tech Stack

| 분류 | 기술 스택 |
| :--- | :--- |
| **Language** | ![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=Python&logoColor=white) |
| **Framework** | ![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=FastAPI&logoColor=white) |
| **Database** | ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat-square&logo=PostgreSQL&logoColor=white) (Supabase) |
| **ORM** | ![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00?style=flat-square&logo=SQLAlchemy&logoColor=white) |
| **AI / LLM** | ![OpenAI](https://img.shields.io/badge/OpenAI-412991?style=flat-square&logo=OpenAI&logoColor=white) (GPT-4o) |
| **Doc Gen** | `docxtpl` (Word Template Rendering) |

<br/>

## ✨ Key Features

### 1. AI 법률 상담 및 정보 추출 (RAG + Smart Extraction)
- **RAG (Retrieval-Augmented Generation):** 사용자가 법률적인 질문을 하면 관련 법령(Tip List)을 검색하여 정확한 근거를 바탕으로 답변합니다.
- **Smart Extraction:** 대화 내용에서 계약서 작성에 필요한 핵심 데이터(이름, 날짜, 금액, 주소 등)를 AI가 자동으로 추출하여 DB에 저장합니다.
- **동적 시나리오 핸들링:** '근로계약서', '통합신청서', '임대차계약서' 등 문서 종류에 따라 특화된 질문 시나리오와 분기 처리(Skip Logic)를 수행합니다.

### 2. 문서 자동 완성 및 다운로드
- **실시간 미리보기:** 추출된 데이터를 바탕으로 완성될 문서의 HTML 미리보기를 제공합니다.
- **DOCX 생성:** `.docx` 템플릿에 데이터를 매핑하여, 체크박스(Wingdings) 및 텍스트가 완벽하게 입력된 워드 파일을 생성합니다.

### 3. 지원 문서 양식
- **표준근로계약서**
- **통합신청서(신고서)** (출입국관리법 별지 제34호 서식)
- **부동산임대차계약서**

<br/>

## 📂 Project Structure

```bash
📦 app
 ┣ 📂 ai_handlers       # AI 로직 핸들러 (문서별 분기 처리)
 ┃ ┣ 📜 attorney_ai.py
 ┃ ┣ 📜 foreign_ai.py   # 통합신청서 로직
 ┃ ┣ 📜 lease_ai.py     # 임대차계약서 로직
 ┃ ┗ 📜 working_ai.py   # 근로계약서 로직
 ┣ 📂 routers           # API 엔드포인트
 ┃ ┣ 📜 contracts.py    # 계약서 생성/조회/채팅 API
 ┃ ┗ 📜 users.py        # 사용자 관련 API
 ┣ 📂 templates         # .docx 및 .html 서식 파일
 ┣ 📜 crud.py           # DB CRUD 작업
 ┣ 📜 database.py       # DB 연결 설정 (AsyncSession)
 ┣ 📜 main.py           # FastAPI 진입점
 ┣ 📜 models.py         # SQLAlchemy 모델 정의
 ┣ 📜 schemas.py        # Pydantic 스키마 (Req/Res)
 ┗ 📜 services.py       # 비즈니스 로직 통합
