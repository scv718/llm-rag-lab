# LLM RAG Lab

프로젝트 단위로 문서 PDF와 소스코드 ZIP을 업로드하고, 선택한 타깃에 대해 근거 기반 질의응답을 제공하는 RAG 분석 도구입니다.  
단순 벡터 검색 예제가 아니라, 코드 검색 품질 개선과 검색 파이프라인 구조화에 초점을 둔 포트폴리오 프로젝트입니다.

## 요약

- 프로젝트별 활성 타깃을 관리하는 문서/코드 분석형 RAG
- PDF 문서와 코드 ZIP을 각각 다른 ingest 전략으로 처리
- 코드 질의에는 `keyword + vector + reranking` 조합 적용
- Streamlit UI, FastAPI API, SQLite 메타데이터, Chroma 벡터 저장소로 구성
- 검색 품질 로직에 대한 테스트와 경량 평가 스크립트 포함

## 포트폴리오 관점 핵심 메시지

이 프로젝트는 "LLM API를 붙여본 데모"보다, 코드 검색에서 retrieval 품질을 어떻게 개선했는지를 보여주는 데 초점을 둡니다.

- 문서 검색과 코드 검색의 ingest 전략을 분리함
- 프로젝트 단위 scope와 활성 자산 개념으로 검색 범위를 명시적으로 제어함
- 코드 질의에서 `keyword + vector + reranking`을 결합해 path, symbol, exact phrase 신호를 함께 활용함
- 테스트와 평가 스크립트로 검색 품질 개선 근거를 남김

## 문제 정의

일반적인 RAG 데모는 "파일 업로드 -> 임베딩 -> 벡터 검색 -> LLM 응답" 수준에서 끝나는 경우가 많습니다.  
하지만 코드 검색에서는 벡터 유사도만으로 원하는 위치를 정확히 찾기 어려운 경우가 많습니다.

이 프로젝트는 다음 문제를 해결하려는 방향으로 설계했습니다.

- 프로젝트별로 검색 대상을 분리하고 UI 상태와 검색 범위를 일치시킬 것
- 문서와 코드의 ingest 전략을 분리할 것
- 코드 검색에서 심볼명, 경로명, exact phrase 같은 명시적 힌트를 활용할 것
- retrieval 로직을 분리해서 실험과 품질 평가가 가능하게 만들 것

## 핵심 기능

- 프로젝트 생성 및 활성 검색 타깃 선택
- PDF 업로드, 페이지 단위 텍스트 추출, 문자 기반 청킹
- ZIP 업로드, 안전한 압축 해제, 소스 파일 라인 기반 청킹
- `BAAI/bge-small-en-v1.5` 임베딩 기반 벡터 검색
- 코드 대상 키워드 검색
- 심볼 힌트, 경로 relevance, exact phrase를 반영한 재랭킹
- Gemini 기반 최종 답변 생성
- citation, score, 검색 힌트 정보 반환
- Streamlit 기반 대화형 UI

## 차별화 포인트

### 1. 프로젝트 스코프 검색

UI에는 프로젝트가 있는데 서버는 마지막 업로드 전역 상태만 보는 구조는 흔한 MVP 패턴입니다.  
이 프로젝트는 기본적으로 프로젝트 전체검색을 수행하고, 필요할 때만 활성 자산 선택으로 검색 범위를 좁힐 수 있도록 구성했습니다.

### 2. 코드 검색 재랭킹

코드 질의에서는 단순 벡터 거리만으로 결과를 쓰지 않습니다. 다음 요소를 반영해 검색 결과를 다시 정렬합니다.

- keyword hit 수
- symbol hint 포함 여부
- 파일 경로 relevance
- exact phrase 일치 여부
- 벡터 distance

즉, "RAG를 붙였다"보다 "검색 품질을 어떻게 끌어올렸는가"에 더 무게를 둔 구조입니다.

### 3. retrieval 계층 분리

ingest, retrieval, generation을 서비스 계층으로 분리했습니다.

- `file_services.py`: 업로드 ingest
- `retrieval_service.py`: 검색 파이프라인
- `rag_service.py`: target 해석과 generation

이렇게 분리해두면 검색 전략을 바꾸거나 평가 로직을 추가할 때 영향 범위를 줄일 수 있습니다.

## 아키텍처

```text
Streamlit UI
  -> FastAPI API
    -> Upload / Ask endpoint
      -> Ingest service
      -> Retrieval service
      -> Gemini generation
        -> SQLite metadata
        -> Chroma vector store
        -> Local embedding model
```

## 검색 흐름

### 문서 PDF

1. PDF 업로드
2. 페이지별 텍스트 추출
3. 문자 기반 청킹
4. 임베딩 생성
5. Chroma 저장
6. 질문 시 벡터 검색
7. 검색 결과를 LLM 프롬프트에 주입

### 코드 ZIP

1. ZIP 업로드
2. 안전한 압축 해제
3. 소스 파일 탐색 및 라인 기반 청킹
4. 임베딩 생성
5. Chroma 저장
6. 질문 시 벡터 검색 + 키워드 검색 수행
7. 심볼/경로/구문 힌트를 반영해 재랭킹
8. 상위 결과를 LLM 프롬프트에 주입

## 기술 스택

- Python 3.11
- FastAPI
- Streamlit
- ChromaDB
- sentence-transformers
- BAAI/bge-small-en-v1.5
- Google Gemini API
- SQLite
- PyPDF2
- `requirements-extra.txt`로 문서 파서 의존성 분리 관리

## 프로젝트 구조

```text
llm-rag-lab/
├── app/
│   ├── core/        # 설정, 전역 상태
│   ├── db/          # SQLite repository 계층
│   ├── services/    # ingest / retrieval / reranking / API client
│   ├── ui/          # Streamlit 화면
│   ├── utils/       # 공통 유틸
│   └── main.py      # FastAPI entrypoint
├── data/            # 업로드 파일 / 벡터 저장소
├── tests/           # 검색 로직 테스트 / fixture
├── tools/           # 경량 평가 스크립트
├── requirements.txt
└── README.MD
```

## 실행 방법

### 1. 환경 준비

`.env` 예시:

```env
GEMINI_API_KEY=your_api_key
USE_REAL_API=true
UPLOAD_API_URL=http://127.0.0.1:8000/upload
RAG_API_URL=http://127.0.0.1:8000/rag/ask
```

### 2. 설치

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

문서/오피스 포맷 파서를 함께 쓰려면 추가 설치:

```bash
pip install -r requirements-extra.txt
```

추가 의존성 범위:

- `python-docx`: `docx`
- `openpyxl`: `xlsx`
- `python-pptx`: `pptx`
- `PyPDF2`: `pdf` 및 ZIP 내부 PDF

### 실행 전 정리

레포에는 런타임 산출물을 커밋하지 않는 것을 기본 원칙으로 둡니다.

- `llm_ui.db`
- `data/uploads/`
- `data/repos/`
- `data/chroma_db/`
- `data/projects/`

위 경로는 `.gitignore`에 포함되어 있으며, 로컬 실행 중 생성됩니다.

### 3. FastAPI 실행

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 4. Streamlit 실행

```bash
streamlit run app/ui/app_ui.py
```

## API 예시

### `POST /upload`

지원 업로드 형식:

- 문서형: `pdf`, `txt`, `md`, `docx`, `csv`, `xlsx`
- 코드형: `zip`, 단일 코드파일 `java`, `py`, `js`, `ts`, `xml`, `yml`, `yaml`, `sql`

ZIP 내부에서도 다음 형식은 내용 추출 대상입니다.

- 평문/코드: `txt`, `md`, `csv`, `java`, `py`, `js`, `ts`, `xml`, `yml`, `yaml`, `json`, `sql` 등
- 문서형: `pdf`, `docx`, `xlsx`, `pptx`

단, ZIP 내부 `docx/xlsx/pptx/pdf` 추출은 `requirements-extra.txt` 설치가 필요할 수 있습니다.

`project_id`가 있으면 해당 프로젝트의 활성 타깃을 갱신합니다.

응답 예시:

```json
{
  "status": "success",
  "kind": "code",
  "project_id": 1,
  "repo_id": "xxxxxxxxxxxxxxxx",
  "filename": "project.zip",
  "extracted_files": 143,
  "uncompressed_bytes": 2481932,
  "chunks": 320,
  "indexed": 320
}
```

### `POST /rag/ask`

질문을 입력하면 프로젝트의 활성 타깃 기준으로 retrieval 후 응답을 생성합니다.
기본 `top_k`는 10이며, 서버 설정 상한은 `RETRIEVAL_LIMIT` 환경변수로 제어합니다.

요청 예시:

```json
{
  "project_id": 1,
  "question": "AuthController에서 /api/login 처리 위치 알려줘",
  "top_k": 10
}
```

응답 예시:

```json
{
  "answer": "...",
  "citations": [
    {
      "kind": "code",
      "path": "auth/controller/AuthController.java",
      "start_line": 42,
      "end_line": 88,
      "distance": 0.1234,
      "score": 4.8
    }
  ],
  "target": {
    "kind": "code",
    "id": "xxxxxxxxxxxxxxxx",
    "filename": "project.zip",
    "project_id": 1
  },
  "keywords": ["AuthController", "/api/login"],
  "symbol_hints": ["AuthController"]
}
```

## 품질 검증

검색 관련 핵심 로직은 테스트와 경량 평가 스크립트로 검증할 수 있습니다.

```bash
python3 -m unittest tests/test_search_services.py
python3 tools/eval_search_quality.py tests/fixtures/search_eval_cases.json
```

현재 포함된 검증 포인트:

- 키워드 추출
- 심볼 힌트 추출
- 경로/심볼 기반 재랭킹
- top-1 경로 정확도 샘플 평가

정량 지표 예시는 `tools/eval_search_quality.py`와 `tests/fixtures/search_eval_cases.json`으로 재현할 수 있습니다.
README에는 수치를 고정해 적지 않았지만, 향후에는 rerank 적용 전후 top-1 정확도 비교를 계속 추가할 계획입니다.

## 구현하면서 신경 쓴 점

- ZIP ingest 시 Zip Slip 방지와 압축 해제 용량 제한 추가
- 문서와 코드의 청킹 전략 분리
- UI 프로젝트 상태와 서버 검색 범위를 일치시키는 target 모델 도입
- retrieval 결과에 score를 남겨 디버깅 가능성 확보
- generation 이전의 retrieval 계층을 독립시켜 실험 가능한 구조 유지

## 한계

- 현재 평가는 샘플 케이스 기반이라 충분한 규모의 질의셋은 아직 없음
- 임베딩 모델이 영어 중심이라 한국어 코드 질의 최적화 여지가 있음
- 인증/권한 관리, 운영 로그, 관측성은 미구현
- 비동기 ingest 큐나 대규모 인덱싱 처리는 아직 없음

## 다음 개선 방향

- 평가 질의셋 확대 및 검색 품질 지표 정량화
- 함수/클래스 단위 구조적 청킹 추가
- 다중 타깃 동시 검색과 결과 통합
- 임베딩 모델 다국어 대응
- Docker 기반 실행 환경 정리
- LLM provider 추상화

## 포트폴리오 보강 우선순위

실무형 포트폴리오로 더 강하게 보이게 하려면 아래 순서로 보강하는 것이 효율적입니다.

1. 런타임 산출물 완전 제외와 레포 정리
2. Docker 또는 단일 실행 스크립트로 재현성 고정
3. 검색 품질 전후 비교 지표를 README에 추가
4. 구조 질문 / 위치 질문 / 흐름 질문 단위 평가셋 확대

## 포트폴리오 관점에서 보여줄 수 있는 것

- RAG 파이프라인을 end-to-end로 구현한 경험
- 문서 검색과 코드 검색의 ingest/retrieval 전략을 다르게 설계한 경험
- 흔한 RAG 예제를 넘어서 검색 품질 개선 로직을 직접 설계한 경험
- 프로젝트 스코프 상태 관리와 API/UI 연동을 구조적으로 정리한 경험
- 테스트와 평가 스크립트로 개선 근거를 남기는 방식의 개발 경험
