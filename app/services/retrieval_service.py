from dataclasses import dataclass

from app.core.config import DEFAULT_RETRIEVAL_LIMIT, REPO_DIR, SEARCH_RERANK_LIMIT, vs
from app.services.embeddings import embed_query
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

    where = None
    repo_extract_dir = None

    if target["kind"] == "doc":
        where = {"$and": [{"kind": "doc"}, {"doc_id": target["id"]}]}
    elif target["kind"] == "code":
        where = {"$and": [{"kind": "code"}, {"repo_id": target["id"]}]}
        repo_extract_dir = REPO_DIR / target["id"]

    vector_hits = vs.query(query_embedding=query_vector, n_results=effective_top_k, where=where)

    keyword_hits = []
    if target["kind"] == "code" and repo_extract_dir:
        keyword_hits = keyword_search_in_repo(
            repo_dir=repo_extract_dir,
            keywords=keywords,
            limit=200,
        )

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
