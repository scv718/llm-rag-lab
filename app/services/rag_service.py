import traceback

from fastapi import HTTPException

from app.core.config import (
    DEFAULT_LLM_SETTINGS,
    DEFAULT_RETRIEVAL_LIMIT,
    LLM_MODEL,
    LLM_PROVIDER,
    LOCAL_LLM_MODEL,
)
from app.db.doc_repo import list_project_docs
from app.db.repo_repo import list_project_repos
from app.db.target_repo import get_project_target_settings, list_project_targets
from app.services.llm_provider import LLMSettings, create_llm_provider
from app.services.retrieval_service import retrieve_context


def ask_rag(
    question: str,
    top_k: int,
    project_id: int | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
) -> dict:
    try:
        question = question.strip()
        top_k = max(1, min(int(top_k), DEFAULT_RETRIEVAL_LIMIT))
        provider_name, model_name = resolve_llm_selection(llm_provider, llm_model)
        top_k = adjust_top_k_for_provider(top_k, provider_name)
        llm = create_llm_provider(
            LLMSettings(
                provider=provider_name,
                model=model_name,
                gemini_api_key=DEFAULT_LLM_SETTINGS.gemini_api_key,
                openai_base_url=DEFAULT_LLM_SETTINGS.openai_base_url,
                openai_api_key=DEFAULT_LLM_SETTINGS.openai_api_key,
            )
        )

        target = resolve_target(project_id)
        if not target:
            raise HTTPException(status_code=400, detail="질문할 대상을 먼저 업로드하세요.")

        retrieval = retrieve_context(question=question, target=target, top_k=top_k)
        system = build_system_prompt(provider_name)
        user_prompt = build_user_prompt(question, retrieval.context, provider_name)

        return {
            "answer": llm.generate_text(system, user_prompt),
            "citations": retrieval.citations,
            "retrieved_k": len(retrieval.ranked_hits),
            "target": target,
            "keywords": retrieval.keywords,
            "symbol_hints": retrieval.symbol_hints,
            "keyword_hits": len(retrieval.keyword_hits),
            "vector_hits": len(retrieval.vector_hits),
            "llm_provider": provider_name,
            "llm_model": model_name,
            "ranking_debug": retrieval.to_debug_payload(),
        }

    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="RAG 처리 중 오류가 발생했습니다.") from exc


def resolve_target(project_id: int | None) -> dict:
    if project_id is None:
        raise HTTPException(status_code=400, detail="project_id는 필수입니다. 프로젝트를 선택한 뒤 다시 질문하세요.")

    docs = list_project_docs(project_id)
    repos = list_project_repos(project_id)
    if not docs and not repos:
        return {}

    target_settings = get_project_target_settings(project_id)
    active_targets = list_project_targets(project_id)
    active_only = bool(target_settings["active_only"]) if target_settings else False

    if active_only and not active_targets:
        raise HTTPException(status_code=400, detail="활성 자산 검색이 켜져 있습니다. 먼저 활성 자산을 선택하세요.")

    return {
        "kind": "project",
        "id": str(project_id),
        "filename": f"project-{project_id}",
        "project_id": project_id,
        "active_only": active_only,
        "active_targets": active_targets,
        "doc_count": len(docs),
        "repo_count": len(repos),
    }


def resolve_llm_selection(llm_provider: str | None, llm_model: str | None) -> tuple[str, str]:
    provider = (llm_provider or LLM_PROVIDER).strip().lower()
    model = (llm_model or "").strip()

    if provider == "local":
        return provider, model or LOCAL_LLM_MODEL

    return provider, model or LLM_MODEL


def build_system_prompt(provider_name: str) -> str:
    base_prompt = (
        "당신은 한국어로 답변하는 백엔드 전문가입니다. "
        "다음 우선순위를 반드시 지키세요. "
        "1순위는 근거 없는 내용 생성 금지입니다. "
        "2순위는 실제 코드와 설정 근거 우선입니다. "
        "3순위는 구조화된 답변 유지입니다. "
        "4순위는 가능한 범위에서 충분히 설명하는 것입니다. "
        "반드시 제공된 [참고 발췌] 범위 안에서만 답하세요. "
        "참고 발췌에는 keyword 검색 결과와 vector 검색 결과가 함께 포함될 수 있습니다. "
        "검색 결과에는 score가 포함될 수 있으며 score가 높은 근거를 우선 활용하세요. "
        "파일 경로, 줄 번호, 코드 라인이 있으면 우선적으로 활용하세요. "
        "ZIP 또는 코드 자산에 대해서는 파일 이름만 보고 추정하지 말고, 내부 파일의 실제 코드 내용이 있는 근거를 우선 사용하세요. "
        "경로(path) 근거만으로는 구조 설명 정도만 하고, 동작/흐름/로직 설명은 하지 마세요. "
        "근거가 부족하면 부족하다고 말하세요. "
        "코드 근거가 있는 내용만 단정적으로 말하고, 추정은 '추정'이라고 명시하세요. "
        "포트, 엔드포인트, 설정 키, 클래스 역할 같은 핵심 주장에는 가능하면 괄호로 근거 파일명을 붙이세요. "
        "답변 형식은 질문 성격에 맞게 조절하되, 구조 질문이면 가능하면 아래 틀을 따르세요. "
        "1. 전체 개요 "
        "2. 패키지 구조 "
        "3. 주요 클래스와 역할 "
        "4. 요청/데이터 흐름 "
        "5. 설정/포트/연동 포인트 "
        "6. 확인되지 않은 부분 "
        "질문 성격상 맞지 않는 항목은 생략할 수 있습니다."
    )

    if provider_name != "local":
        return base_prompt

    local_prompt = (
        "로컬 모델은 짧게 요약해 끝내지 말고, 확인된 실제 이름과 설정값을 우선 쓰세요. "
        "확인된 파일이나 클래스가 충분할 때만 여러 개를 설명하고, 부족하면 부족하다고 명시하세요. "
        "특히 구조 설명에서는 클래스명만 나열하지 말고 연결 관계를 설명하세요."
    )

    return f"{base_prompt} {local_prompt}"


def build_user_prompt(question: str, retrieval_context: str, provider_name: str) -> str:
    base_prompt = (
        f"질문:\n{question}\n\n"
        "출력 규칙:\n"
        "- 답변은 한국어로만 작성\n"
        "- 마크다운 제목과 불릿을 사용해 읽기 쉽게 정리\n"
        "- 패키지/클래스/설정 파일은 가능한 한 실제 이름을 그대로 표기\n"
        "- 단순 파일 나열이 아니라 역할과 연결 관계를 설명\n"
        "- 참고 발췌에 없는 엔드포인트, 클래스명, DTO, 포트 번호를 새로 만들지 말기\n"
        "- 확인된 근거가 약한 항목은 `확인되지 않음` 또는 `추정`으로 표시\n"
        "- 포트, 엔드포인트, 설정 키, 핵심 클래스 역할은 가능하면 `(근거: 파일명)` 형식으로 표시\n"
    )

    if provider_name != "local":
        return f"{base_prompt}\n\n{retrieval_context}"

    local_example = """
좋은 답변 예시:
## 1. 전체 개요
foo 프로젝트는 메시지 중계용 백엔드 애플리케이션이며 `FooApplication.java`가 진입점입니다 `(근거: FooApplication.java)`. HTTP 요청을 받아 서비스 계층으로 전달하고, 일부 데이터는 UDP 송신기로 넘기는 구조입니다 `(근거: FooController.java, FooSender.java)`.

## 2. 패키지 구조
- `com.example.foo.controller`: 외부 요청을 받는 REST 컨트롤러가 위치합니다.
- `com.example.foo.service`: 핵심 비즈니스 로직 인터페이스와 구현체가 위치합니다.
- `com.example.foo.config`: 포트와 외부 서버 주소 같은 실행 설정을 로드합니다.

## 3. 주요 클래스와 역할
- `FooController.java`: `/v1/foo` 요청을 받아 `FooService` 호출로 연결합니다.
- `FooServiceImpl.java`: 요청을 해석하고 DTO를 조합해 후속 처리로 넘깁니다.
- `FooConfig.java`: `application-dev.yml` 값을 바인딩합니다.

## 4. 요청 흐름
1. `FooController.java`가 HTTP 요청을 수신합니다.
2. `FooServiceImpl.java`가 요청을 처리합니다.

## 5. 설정/포트/연동 포인트
- `application-dev.yml`에서 HTTP 포트와 외부 서버 주소를 관리합니다.

## 6. 확인되지 않은 부분
- 코드 근거가 없는 내부 알고리즘은 추정이라고 구분합니다.

나쁜 답변 예시:
- 클래스 이름만 짧게 나열
- 포트 번호나 설정 파일명을 빼먹음
- 흐름 설명 없이 "처리한다"로 끝냄
""".strip()

    local_rules = (
        "\n추가 규칙:\n"
        "- [프로젝트 개요] 블록이 있으면 그 안의 roles(entry/input/process/output/config)와 패키지, 설정 키를 먼저 읽고 본문 구조에 반영하기\n"
        "- 위 좋은 답변 예시처럼 확인된 실제 이름과 역할을 함께 적기\n"
        "- 확인된 파일이나 클래스가 4개 이상이면 4개 이상 설명하고, 부족하면 부족하다고 명시하기\n"
        "- 포트 번호, 엔드포인트, 설정 키가 보이면 숫자와 이름을 그대로 쓰기\n"
        "- 참고 발췌에 없는 `/path`, 클래스명, 설정 키는 추측해서 쓰지 말고 '확인되지 않음'으로 처리하기\n"
        "- `추정`, `확인됨`을 구분해 표현하기\n"
        "- 분량보다 사실성을 우선하고, 근거가 부족하면 짧아져도 괜찮음\n\n"
        f"{local_example}\n\n"
        f"{retrieval_context}"
    )

    return f"{base_prompt}{local_rules}"


def adjust_top_k_for_provider(top_k: int, provider_name: str) -> int:
    if provider_name == "local":
        return min(top_k, 16)
    return top_k
