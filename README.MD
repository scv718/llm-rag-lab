# LLM RAG Lab

FastAPI + Chroma(Vector DB) + Google Gemini API 기반의  
Retrieval-Augmented Generation(RAG) 서비스 예제 프로젝트입니다.

본 프로젝트는 다음을 목표로 합니다:

- RAG 파이프라인 구조 설계
- 벡터 데이터베이스 기반 문서 검색
- 검색된 문맥을 LLM 프롬프트에 주입
- FastAPI 기반 서비스화
- 환경 재현 가능한 개발 구조 구성

---

## 🏗 시스템 아키텍처

Client  
↓  
FastAPI  
↓  
Chroma (Vector Store - 영속 저장)  
↓  
Gemini API (임베딩 + 응답 생성)

---

## 🚀 주요 기능

- 문서 저장(ingest) API
- Chroma 기반 영속 벡터 저장소
- 의미 기반 유사도 검색
- 검색 결과 기반 LLM 응답 생성
- .env 기반 환경 변수 관리
- 서비스 구조 분리 설계

---

## 🧰 기술 스택

- Python 3.11
- FastAPI
- Uvicorn
- ChromaDB
- Google Gemini API (google-genai SDK)
- python-dotenv

---

## 📦 개발 환경 요구사항

- Python 3.11.x 권장
- Windows / macOS / Linux

설치된 Python 버전 확인:

```powershell
py -0
```

---

## ⚙ 설치 방법 (Windows 기준)

### 1️⃣ Python 3.11 기반 가상환경 생성

```powershell
py -3.11 -m venv venv
venv\Scripts\activate
```

### 2️⃣ pip 최신화

```powershell
python -m pip install -U pip
```

### 3️⃣ 패키지 설치

```powershell
pip install -r requirements.txt
```

---

## 🔑 환경 변수 설정

프로젝트 루트에 `.env` 파일 생성:

```
GEMINI_API_KEY=발급받은_API_키
CHROMA_DIR=./data/chroma
GEMINI_MODEL=gemini-3-flash-preview
GEMINI_EMBED_MODEL=text-embedding-004
```

---

## ▶ 서버 실행

```powershell
uvicorn app.main:app --reload
```

Swagger 접속:

http://127.0.0.1:8000/docs

---

## 📥 API 명세

### POST /ingest

문서를 벡터 DB에 저장합니다.

요청 예시:

```json
{
  "id": "doc1",
  "text": "이 문서는 RAG 구조를 설명합니다.",
  "meta": "manual"
}
```

---

### POST /chat

질문을 입력하면, 관련 문서를 검색한 뒤  
해당 문맥을 기반으로 LLM이 응답을 생성합니다.

요청 예시:

```json
{
  "message": "RAG가 무엇인가요?"
}
```

응답 예시:

```json
{
  "answer": "...",
  "contexts": ["검색된 문서1", "검색된 문서2"]
}
```

---

## 📂 프로젝트 구조

```
llm-rag-lab/
│
├── app/
│   ├── main.py
│   ├── rag.py
│   └── gemini_client.py
│
├── data/
│   └── chroma/   (벡터 DB 저장 경로)
│
├── .env
├── requirements.txt
└── README.md
```

---

## 🎯 프로젝트 목적

본 프로젝트는 다음 역량을 증명하기 위해 제작되었습니다:

- LLM 기반 서비스 아키텍처 이해
- 벡터 검색 기반 RAG 설계
- 외부 LLM API 연동
- 환경 재현 가능한 개발 구조 구성
- FastAPI 기반 서비스화 경험

---

## 🔮 향후 확장 계획

- LLMClient 인터페이스 추상화 (Gemini / OpenAI / Local LLM 교체 가능 구조)
- FAISS 기반 검색 방식 비교
- 로컬 LLM 성능 비교 분석
- Docker 기반 컨테이너화
- 클라우드 배포 (GCP VM)

---

## 📌 참고

본 프로젝트는 학습 및 포트폴리오 목적의 실험적 구현입니다.