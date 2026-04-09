from dataclasses import dataclass

from app.core.config import DEFAULT_RETRIEVAL_LIMIT, REPO_DIR, SEARCH_RERANK_LIMIT, vs
from app.db.doc_repo import list_project_docs
from app.db.repo_repo import list_project_repos
from app.services.embeddings import embed_query
from app.services.project_scope import build_project_scope, select_project_assets
from app.services.repo_intel import (
    build_repo_overview_context,
    classify_question_type,
    recommended_rerank_limit,
)
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
    scope: dict
    question_type: str
    keywords: list[str]
    symbol_hints: list[str]
    vector_hits: list[dict]
    keyword_hits: list[dict]
    merged_hits: list[dict]
    ranked_hits: list[dict]
    context: str
    citations: list[dict]
    repo_overview: str

    def to_debug_payload(self) -> dict:
        return {
            "scope": self.scope,
            "question_type": self.question_type,
            "keywords": self.keywords,
            "symbol_hints": self.symbol_hints,
            "vector_hits": len(self.vector_hits),
            "keyword_hits": len(self.keyword_hits),
            "merged_hits": len(self.merged_hits),
            "ranked_hits": len(self.ranked_hits),
            "repo_overview": bool(self.repo_overview),
            "context_chars": len(self.context),
        }


def retrieve_context(question: str, target: dict, top_k: int) -> RetrievalResult:
    effective_top_k = max(1, min(int(top_k), DEFAULT_RETRIEVAL_LIMIT))
    query_vector = embed_query(question)
    question_type = classify_question_type(question)
    keywords = extract_search_keywords(question)
    symbol_hints = extract_symbol_hints(question)

    docs, repos, repo_dirs = resolve_target_assets(target)
    vector_hits = query_vector_hits(query_vector=query_vector, top_k=effective_top_k, target=target, docs=docs, repos=repos)
    keyword_hits = query_keyword_hits(keywords=keywords, repo_dirs=repo_dirs)

    merged_hits = merge_search_results(keyword_hits, vector_hits)
    rerank_limit = recommended_rerank_limit(question, len(repos), SEARCH_RERANK_LIMIT)
    ranked_hits = rerank_search_results(
        question=question,
        keywords=keywords,
        symbol_hints=symbol_hints,
        merged_hits=merged_hits,
        limit=rerank_limit,
    )
    context, citations = build_context_and_citations(ranked_hits)
    repo_overview, repo_citations = build_repo_overview_context(question, repos)
    if repo_overview:
        context = f"{repo_overview}\n\n{context}"
        citations = repo_citations + citations

    return RetrievalResult(
        scope=build_scope_debug(target, docs, repos, repo_dirs),
        question_type=question_type,
        keywords=keywords,
        symbol_hints=symbol_hints,
        vector_hits=vector_hits,
        keyword_hits=keyword_hits,
        merged_hits=merged_hits,
        ranked_hits=ranked_hits,
        context=context,
        citations=citations,
        repo_overview=repo_overview,
    )


def resolve_target_assets(target: dict) -> tuple[list, list, list]:
    if target.get("project_id") is None:
        kind = target.get("kind")
        if kind == "doc":
            return [{"doc_id": target["id"], "filename": target.get("filename", "")}], [], []
        if kind == "code":
            repo = {"repo_id": target["id"], "filename": target.get("filename", "")}
            return [], [repo], [REPO_DIR / repo["repo_id"]]
        return [], [], []

    project_id = int(target["project_id"])
    active_only = bool(target.get("active_only"))
    active_targets = target.get("active_targets", [])

    docs = list_project_docs(project_id)
    repos = list_project_repos(project_id)
    docs, repos = select_project_assets(active_only, active_targets, docs, repos)
    _, repo_dirs = build_project_scope(project_id, active_only, active_targets, docs, repos, REPO_DIR)
    return docs, repos, repo_dirs


def query_vector_hits(*, query_vector: list[float], top_k: int, target: dict, docs: list, repos: list) -> list[dict]:
    asset_count = max(1, len(docs) + len(repos))
    per_asset_top_k = max(3, min(top_k, DEFAULT_RETRIEVAL_LIMIT // asset_count or top_k))

    hits = []
    if target.get("project_id") is not None:
        where, _ = build_project_scope(
            int(target["project_id"]),
            bool(target.get("active_only")),
            target.get("active_targets", []),
            docs,
            repos,
            REPO_DIR,
        )
        hits.extend(
            vs.query(
                query_embedding=query_vector,
                n_results=max(top_k * 3, per_asset_top_k),
                where=where,
            )
        )
    else:
        for doc in docs:
            hits.extend(
                vs.query(
                    query_embedding=query_vector,
                    n_results=per_asset_top_k,
                    where={"$and": [{"kind": "doc"}, {"doc_id": doc["doc_id"]}]},
                )
            )

        for repo in repos:
            hits.extend(
                vs.query(
                    query_embedding=query_vector,
                    n_results=per_asset_top_k,
                    where={"$and": [{"kind": "code"}, {"repo_id": repo["repo_id"]}]},
                )
            )

    deduped = []
    seen = set()
    for hit in sorted(hits, key=lambda item: item.get("distance", 1.0)):
        metadata = hit.get("metadata", {})
        chunk_id = metadata.get("chunk_id")
        key = chunk_id or (
            metadata.get("kind"),
            metadata.get("doc_id"),
            metadata.get("repo_id"),
            metadata.get("path"),
            metadata.get("page"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(hit)

    return deduped[: max(top_k * 3, top_k)]


def query_keyword_hits(*, keywords: list[str], repo_dirs: list) -> list[dict]:
    if not repo_dirs:
        return []

    keyword_hits = []
    per_repo_limit = max(50, 200 // max(1, len(repo_dirs)))
    for repo_extract_dir in repo_dirs:
        keyword_hits.extend(
            keyword_search_in_repo(
                repo_dir=repo_extract_dir,
                keywords=keywords,
                limit=per_repo_limit,
            )
        )
    return keyword_hits[:200]


def build_scope_debug(target: dict, docs: list, repos: list, repo_dirs: list) -> dict:
    return {
        "kind": target.get("kind"),
        "project_id": target.get("project_id"),
        "active_only": bool(target.get("active_only")),
        "active_targets": len(target.get("active_targets", [])),
        "doc_count": len(docs),
        "repo_count": len(repos),
        "repo_dirs": len(repo_dirs),
    }
