import traceback

from fastapi import HTTPException

from app.core.config import DEFAULT_RETRIEVAL_LIMIT, GEMINI_MODEL, gen_client
from app.core.state import latest_target
from app.db.target_repo import get_project_target
from app.services.retrieval_service import retrieve_context


def ask_rag(question: str, top_k: int, project_id: int | None = None) -> dict:
    try:
        question = question.strip()
        top_k = max(1, min(int(top_k), DEFAULT_RETRIEVAL_LIMIT))

        target = resolve_target(project_id)
        if not target.get("id"):
            raise HTTPException(status_code=400, detail="질문할 대상을 먼저 업로드하거나 선택하세요.")

        retrieval = retrieve_context(question=question, target=target, top_k=top_k)
        system = (
            "당신은 한국어로 답변하는 백엔드 전문가입니다. "
            "반드시 제공된 [참고 발췌] 범위 안에서만 답하세요. "
            "참고 발췌에는 keyword 검색 결과와 vector 검색 결과가 함께 포함될 수 있습니다. "
            "검색 결과에는 score가 포함될 수 있으며 score가 높은 근거를 우선 활용하세요. "
            "파일 경로, 줄 번호, 코드 라인이 있으면 우선적으로 활용하세요. "
            "근거가 부족하면 부족하다고 말하세요. "
            "마지막에 질문으로 끝내지 마세요."
        )
        prompt = f"[SYSTEM]\n{system}\n\n[USER]\n{question}\n\n{retrieval.context}"

        response = gen_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )

        return {
            "answer": response.text,
            "citations": retrieval.citations,
            "retrieved_k": len(retrieval.ranked_hits),
            "target": target,
            "keywords": retrieval.keywords,
            "symbol_hints": retrieval.symbol_hints,
            "keyword_hits": len(retrieval.keyword_hits),
            "vector_hits": len(retrieval.vector_hits),
            "ranking_debug": retrieval.to_debug_payload(),
        }

    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="RAG 처리 중 오류가 발생했습니다.") from exc


def resolve_target(project_id: int | None) -> dict:
    if project_id is not None:
        row = get_project_target(project_id)
        if not row:
            return {}
        return {
            "kind": row["target_kind"],
            "id": row["target_ref_id"],
            "filename": row["filename"],
            "project_id": project_id,
        }

    if latest_target.get("id"):
        return dict(latest_target)

    return {}
