from dataclasses import dataclass

from app.core.config import DEFAULT_RETRIEVAL_LIMIT, REPO_DIR, SEARCH_RERANK_LIMIT, vs
from app.db.doc_repo import list_project_docs
from app.db.repo_repo import list_project_repos
from app.services.embeddings import embed_query
from app.services.project_scope import build_project_scope as build_multi_target_scope
from app.services.search_services import (
    build_context_and_citations,
    extract_search_keywords,
    extract_symbol_hints,
    keyword_search_in_repo,
    merge_search_results,
    rerank_search_results,
)


@dataclass
class RetrievalResult:
    keywords: list[str]
    symbol_hints: list[str]
    vector_hits: list[dict]
    keyword_hits: list[dict]
    ranked_hits: list[dict]
    context: str
    citations: list[dict]

    def to_debug_payload(self) -> dict:
        return {
            "keywords": self.keywords,
            "symbol_hints": self.symbol_hints,
            "vector_hits": len(self.vector_hits),
            "keyword_hits": len(self.keyword_hits),
            "ranked_hits": len(self.ranked_hits),
        }


def retrieve_context(question: str, target: dict, top_k: int) -> RetrievalResult:
    effective_top_k = max(1, min(int(top_k), DEFAULT_RETRIEVAL_LIMIT))
    query_vector = embed_query(question)
    keywords = extract_search_keywords(question)
    symbol_hints = extract_symbol_hints(question)

    where, repo_extract_dirs = build_project_scope(target)

    vector_hits = vs.query(query_embedding=query_vector, n_results=effective_top_k, where=where)

    keyword_hits = []
    if repo_extract_dirs:
        per_repo_limit = max(50, 200 // max(1, len(repo_extract_dirs)))
        for repo_extract_dir in repo_extract_dirs:
            keyword_hits.extend(
                keyword_search_in_repo(
                    repo_dir=repo_extract_dir,
                    keywords=keywords,
                    limit=per_repo_limit,
                )
            )
        keyword_hits = keyword_hits[:200]

    merged_hits = merge_search_results(keyword_hits, vector_hits)
    ranked_hits = rerank_search_results(
        question=question,
        keywords=keywords,
        symbol_hints=symbol_hints,
        merged_hits=merged_hits,
        limit=SEARCH_RERANK_LIMIT,
    )
    context, citations = build_context_and_citations(ranked_hits)

    return RetrievalResult(
        keywords=keywords,
        symbol_hints=symbol_hints,
        vector_hits=vector_hits,
        keyword_hits=keyword_hits,
        ranked_hits=ranked_hits,
        context=context,
        citations=citations,
    )


def build_project_scope(target: dict) -> tuple[dict | None, list]:
    if target.get("project_id") is None:
        kind = target.get("kind")
        if kind == "doc":
            return {"$and": [{"kind": "doc"}, {"doc_id": target["id"]}]}, []
        if kind == "code":
            return {"$and": [{"kind": "code"}, {"repo_id": target["id"]}]}, [REPO_DIR / target["id"]]
        return None, []

    project_id = int(target["project_id"])
    active_only = bool(target.get("active_only"))
    active_targets = target.get("active_targets", [])

    docs = list_project_docs(project_id)
    repos = list_project_repos(project_id)
    return build_multi_target_scope(project_id, active_only, active_targets, docs, repos, REPO_DIR)
