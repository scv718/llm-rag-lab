import re
from pathlib import Path

from app.services.repo_intel import classify_question_type


PATH_HINT_WORDS = {
    "controller", "service", "repository", "repo", "handler", "router",
    "api", "config", "auth", "login", "security", "user", "admin",
    "payment", "order", "product", "dto", "entity", "model",
}

STRUCTURE_HINT_WORDS = {
    "구조", "아키텍처", "패키지", "디렉터리", "폴더", "트리", "구성", "레이어",
    "structure", "architecture", "package", "packages", "directory", "directories",
    "folder", "folders", "tree", "layout",
}


def rerank_search_results(
    question: str,
    keywords: list[str],
    symbol_hints: list[str],
    merged_hits: list[dict],
    limit: int = 12,
) -> list[dict]:
    question_type = classify_question_type(question)
    scored = []
    for index, hit in enumerate(merged_hits):
        score = score_hit(question, question_type, keywords, symbol_hints, hit)
        enriched = dict(hit)
        enriched["score"] = round(score, 4)
        enriched["rank"] = index + 1
        scored.append(enriched)

    scored.sort(key=lambda item: item["score"], reverse=True)
    return diversify_ranked_hits(question_type, scored, limit=limit)


def score_hit(question: str, question_type: str, keywords: list[str], symbol_hints: list[str], hit: dict) -> float:
    if hit["source"] in {"keyword", "path"}:
        return score_keyword_hit(question, question_type, keywords, symbol_hints, hit)
    return score_vector_hit(question, question_type, keywords, symbol_hints, hit)


def score_keyword_hit(question: str, question_type: str, keywords: list[str], symbol_hints: list[str], hit: dict) -> float:
    matched_keywords = hit.get("matched_keywords", [])
    path = hit.get("path", "")
    text = hit.get("text", "")
    source = hit.get("source", "keyword")

    score = 2.0 if source == "keyword" else 1.2
    score += min(2.5, len(matched_keywords) * 0.9)
    score += path_relevance_score(question_type, question, path)
    score += symbol_relevance_score(question_type, symbol_hints, text, path)
    score += exact_phrase_bonus(question, text)
    score += structure_intent_bonus(question, path, text, source)
    return score


def score_vector_hit(question: str, question_type: str, keywords: list[str], symbol_hints: list[str], hit: dict) -> float:
    metadata = hit.get("metadata", {})
    document = hit.get("document", "")
    distance = float(hit.get("distance", 1.0))
    path = metadata.get("path", metadata.get("filename", ""))

    semantic_base = max(0.0, 1.6 - distance)
    semantic_weight = 1.2 if question_type == "general" else 0.8
    semantic_score = semantic_base * semantic_weight
    keyword_overlap = token_overlap_score(keywords, document, question_type)
    path_score = path_relevance_score(question_type, question, path)
    symbol_score = symbol_relevance_score(question_type, symbol_hints, document, path)

    score = semantic_score + keyword_overlap + path_score + symbol_score
    if metadata.get("kind") == "code" and metadata.get("start_line") is not None:
        score += 0.2
    return score


def token_overlap_score(keywords: list[str], text: str, question_type: str) -> float:
    if not text:
        return 0.0
    lower_text = text.lower()
    hits = sum(1 for keyword in keywords if keyword.lower() in lower_text)
    multiplier = 0.45 if question_type == "general" else 0.3
    cap = 2.4 if question_type == "general" else 2.0
    return min(cap, hits * multiplier)


def path_relevance_score(question_type: str, question: str, path: str) -> float:
    if not path:
        return 0.0

    lower_question = question.lower()
    score = 0.0

    for token in split_path_tokens(path):
        if token in lower_question:
            score += 0.6
        elif token in PATH_HINT_WORDS and token in lower_question:
            score += 0.8

    file_name = Path(path).name.lower()
    if file_name and file_name in lower_question:
        score += 1.2

    if question_type == "structure":
        return min(3.0, score * 1.1)
    return min(2.0, score * 0.85)


def symbol_relevance_score(question_type: str, symbol_hints: list[str], text: str, path: str) -> float:
    if not symbol_hints:
        return 0.0

    haystack = f"{path}\n{text}".lower()
    score = 0.0
    for symbol in symbol_hints:
        lower_symbol = symbol.lower()
        if lower_symbol in haystack:
            score += 1.0
    cap = 2.0 if question_type == "structure" else 3.0
    return min(cap, score)


def exact_phrase_bonus(question: str, text: str) -> float:
    quoted = re.findall(r"'([^']+)'|\"([^\"]+)\"|`([^`]+)`", question)
    phrases = [item for group in quoted for item in group if item]
    if not phrases:
        return 0.0
    lower_text = text.lower()
    matched = sum(1 for phrase in phrases if phrase.lower() in lower_text)
    return min(1.5, matched * 0.75)


def split_path_tokens(path: str) -> list[str]:
    normalized = path.replace("\\", "/").lower()
    raw_tokens = re.split(r"[/_.\-]", normalized)
    return [token for token in raw_tokens if len(token) >= 3]


def structure_intent_bonus(question: str, path: str, text: str, source: str) -> float:
    lower_question = question.lower()
    if not any(token in lower_question for token in STRUCTURE_HINT_WORDS):
        return 0.0

    score = 0.0
    if source == "path":
        score += 1.5

    path_depth = max(0, len([part for part in path.split("/") if part]))
    if path_depth >= 2:
        score += min(1.2, path_depth * 0.15)

    lower_path = path.lower()
    for hint in PATH_HINT_WORDS:
        if hint in lower_path:
            score += 0.2

    if text == path:
        score += 0.4

    return min(3.0, score)


def is_structure_question(question: str) -> bool:
    lower_question = question.lower()
    return any(token in lower_question for token in STRUCTURE_HINT_WORDS)


def diversify_ranked_hits(question_type: str, scored_hits: list[dict], limit: int) -> list[dict]:
    if limit <= 0:
        return []

    if question_type == "structure":
        return scored_hits[:limit]

    non_path_hits = [hit for hit in scored_hits if hit.get("source") != "path"]
    path_hits = [hit for hit in scored_hits if hit.get("source") == "path"]

    selected = []
    if non_path_hits:
        selected.extend(non_path_hits[:limit])
    elif path_hits:
        selected.extend(path_hits[:1])

    remaining_slots = max(0, limit - len(selected))
    if remaining_slots > 0 and path_hits:
        selected.extend(path_hits[: min(remaining_slots, 1)])

    selected.sort(key=lambda item: item["score"], reverse=True)
    return selected[:limit]
