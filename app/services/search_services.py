import os
import re
from pathlib import Path


CODE_EXTENSIONS = {
    ".java", ".kt", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".xml", ".yml", ".yaml", ".properties", ".sql",
    ".cpp", ".c", ".cs", ".go", ".rb", ".php",
}

PATH_HINT_WORDS = {
    "controller", "service", "repository", "repo", "handler", "router",
    "api", "config", "auth", "login", "security", "user", "admin",
    "payment", "order", "product", "dto", "entity", "model",
}


def extract_search_keywords(question: str) -> list[str]:
    q = (question or "").strip()
    if not q:
        return []

    stopwords = {
        "알려줘", "보여줘", "찾아줘", "찾아", "관련", "포함", "포함된",
        "코드", "코드라인", "라인", "부분", "위치", "어디", "어느",
        "있는", "나오는", "사용하는", "사용된", "호출", "호출부",
        "정의", "정의된", "메서드", "함수", "클래스", "문자열",
        "조회", "검색", "전체", "목록", "출력", "좀", "이", "가", "을", "를",
        "은", "는", "의", "에서", "으로", "로", "와", "과"
    }

    results = []
    quoted_patterns = [
        r"'([^']+)'",
        r'"([^"]+)"',
        r"`([^`]+)`",
    ]

    for pattern in quoted_patterns:
        for match in re.findall(pattern, q):
            token = match.strip()
            if token and token not in results:
                results.append(token)

    for match in re.findall(r"(/[A-Za-z0-9_\-./{}]+)", q):
        token = match.strip()
        if token and token not in results:
            results.append(token)

            last_segment = token.rstrip("/").split("/")[-1]
            if last_segment and last_segment not in results:
                results.append(last_segment)

    for match in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{1,}\b", q):
        token = match.strip()
        lower = token.lower()

        if lower in stopwords:
            continue

        if lower in {"code", "line", "lines", "method", "class", "function", "find", "show", "search", "keyword"}:
            continue

        if token not in results:
            results.append(token)

    normalized = re.sub(r"[^\w\s/.\-`\"']", " ", q)
    for raw in normalized.split():
        token = raw.strip()
        if not token:
            continue

        token = re.sub(r"(이|가|을|를|은|는|의|에|에서|으로|로|와|과|도|만|좀)$", "", token)
        if not token:
            continue

        lower = token.lower()
        if token in stopwords or lower in stopwords:
            continue

        if re.search(r"[A-Za-z0-9_/.\-]", token) or len(token) >= 2:
            if token not in results:
                results.append(token)

    ban = {
        "코드", "라인", "부분", "위치", "어디", "관련", "포함", "포함된",
        "사용", "사용된", "정의", "호출", "조회", "검색", "목록", "전체",
    }
    filtered = [token for token in results if token not in ban]
    filtered.sort(key=lambda item: (-len(item), item.lower()))
    return filtered[:8]


def extract_symbol_hints(question: str) -> list[str]:
    hints = []
    for token in extract_search_keywords(question):
        if looks_like_symbol(token) and token not in hints:
            hints.append(token)
    return hints[:8]


def looks_like_symbol(token: str) -> bool:
    return bool(
        re.search(r"[A-Z]", token)
        or "_" in token
        or token.endswith(("Controller", "Service", "Repository", "Handler", "Config"))
    )


def keyword_search_in_repo(repo_dir: Path, keywords: list[str], limit: int = 200) -> list[dict]:
    results = []
    seen = set()

    if not repo_dir.exists() or not keywords:
        return results

    for root, _, files in os.walk(repo_dir):
        for file_name in files:
            ext = Path(file_name).suffix.lower()
            if ext not in CODE_EXTENSIONS:
                continue

            file_path = Path(root) / file_name

            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
                    for line_no, line in enumerate(handle, start=1):
                        line_text = line.rstrip("\n")
                        line_lower = line_text.lower()

                        matched_keywords = [
                            keyword for keyword in keywords
                            if keyword and keyword.lower() in line_lower
                        ]
                        if not matched_keywords:
                            continue

                        rel_path = str(file_path.relative_to(repo_dir)).replace("\\", "/")
                        dedup_key = (rel_path, line_no, line_text.strip())
                        if dedup_key in seen:
                            continue
                        seen.add(dedup_key)

                        results.append(
                            {
                                "source": "keyword",
                                "path": rel_path,
                                "line": line_no,
                                "text": line_text.strip(),
                                "matched_keywords": matched_keywords,
                            }
                        )

                        if len(results) >= limit:
                            return results
            except Exception:
                continue

    return results


def merge_search_results(keyword_hits: list[dict], vector_hits: list[dict]) -> list[dict]:
    merged = []
    seen_keyword_lines = set()

    for hit in keyword_hits:
        merged.append(hit)
        seen_keyword_lines.add((hit["path"], hit["line"]))

    for hit in vector_hits:
        metadata = hit["metadata"]
        if metadata.get("kind") != "code":
            merged.append(
                {
                    "source": "vector",
                    "metadata": metadata,
                    "document": hit["document"],
                    "distance": hit["distance"],
                }
            )
            continue

        path = metadata.get("path")
        start_line = metadata.get("start_line")
        end_line = metadata.get("end_line")

        overlapped = False
        if path and start_line is not None and end_line is not None:
            for keyword_path, keyword_line in seen_keyword_lines:
                if keyword_path == path and start_line <= keyword_line <= end_line:
                    overlapped = True
                    break

        if not overlapped:
            merged.append(
                {
                    "source": "vector",
                    "metadata": metadata,
                    "document": hit["document"],
                    "distance": hit["distance"],
                }
            )

    return merged


def rerank_search_results(
    question: str,
    keywords: list[str],
    symbol_hints: list[str],
    merged_hits: list[dict],
    limit: int = 12,
) -> list[dict]:
    scored = []
    for index, hit in enumerate(merged_hits):
        score = score_hit(question, keywords, symbol_hints, hit)
        enriched = dict(hit)
        enriched["score"] = round(score, 4)
        enriched["rank"] = index + 1
        scored.append(enriched)

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:limit]


def score_hit(question: str, keywords: list[str], symbol_hints: list[str], hit: dict) -> float:
    if hit["source"] == "keyword":
        return score_keyword_hit(question, keywords, symbol_hints, hit)
    return score_vector_hit(question, keywords, symbol_hints, hit)


def score_keyword_hit(question: str, keywords: list[str], symbol_hints: list[str], hit: dict) -> float:
    matched_keywords = hit.get("matched_keywords", [])
    path = hit.get("path", "")
    text = hit.get("text", "")

    score = 2.0
    score += min(2.5, len(matched_keywords) * 0.9)
    score += path_relevance_score(question, path)
    score += symbol_relevance_score(symbol_hints, text, path)
    score += exact_phrase_bonus(question, text)
    return score


def score_vector_hit(question: str, keywords: list[str], symbol_hints: list[str], hit: dict) -> float:
    metadata = hit.get("metadata", {})
    document = hit.get("document", "")
    distance = float(hit.get("distance", 1.0))
    path = metadata.get("path", metadata.get("filename", ""))

    semantic_score = max(0.0, 1.6 - distance)
    keyword_overlap = token_overlap_score(keywords, document)
    path_score = path_relevance_score(question, path)
    symbol_score = symbol_relevance_score(symbol_hints, document, path)

    score = semantic_score + keyword_overlap + path_score + symbol_score
    if metadata.get("kind") == "code" and metadata.get("start_line") is not None:
        score += 0.2
    return score


def token_overlap_score(keywords: list[str], text: str) -> float:
    if not text:
        return 0.0
    lower_text = text.lower()
    hits = sum(1 for keyword in keywords if keyword.lower() in lower_text)
    return min(2.0, hits * 0.35)


def path_relevance_score(question: str, path: str) -> float:
    if not path:
        return 0.0

    lower_question = question.lower()
    lower_path = path.lower()
    score = 0.0

    for token in split_path_tokens(path):
        if token in lower_question:
            score += 0.6
        elif token in PATH_HINT_WORDS and token in lower_question:
            score += 0.8

    file_name = Path(path).name.lower()
    if file_name and file_name in lower_question:
        score += 1.2

    return min(2.5, score)


def symbol_relevance_score(symbol_hints: list[str], text: str, path: str) -> float:
    if not symbol_hints:
        return 0.0

    haystack = f"{path}\n{text}".lower()
    score = 0.0
    for symbol in symbol_hints:
        lower_symbol = symbol.lower()
        if lower_symbol in haystack:
            score += 1.0
    return min(3.0, score)


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


def build_context_and_citations(ranked_hits: list[dict]) -> tuple[str, list[dict]]:
    context_lines = ["[참고 발췌]"]
    citations = []

    for hit in ranked_hits:
        if hit["source"] == "keyword":
            context_lines.append(
                f"- (kind=keyword, score={hit['score']}, path={hit['path']}, line={hit['line']}, keywords={','.join(hit['matched_keywords'])}) {hit['text']}"
            )
            citations.append(
                {
                    "kind": "keyword",
                    "path": hit["path"],
                    "line": hit["line"],
                    "matched_keywords": hit["matched_keywords"],
                    "text": hit["text"],
                    "score": hit["score"],
                }
            )
            continue

        metadata = hit["metadata"]
        document = hit["document"]
        distance = hit["distance"]

        if metadata.get("kind") == "doc":
            context_lines.append(
                f"- (kind=doc, source_type={metadata.get('source_type', 'doc')}, score={hit['score']}, page={metadata.get('page')}, chunk_id={metadata.get('chunk_id', '')}) {document}"
            )
            citations.append(
                {
                    "kind": "doc",
                    "source_type": metadata.get("source_type"),
                    "filename": metadata.get("filename"),
                    "page": metadata.get("page"),
                    "chunk_id": metadata.get("chunk_id"),
                    "chunk_index": metadata.get("chunk_index"),
                    "distance": distance,
                    "score": hit["score"],
                }
            )
        else:
            citations.append(
                {
                    "kind": "code",
                    "source_type": metadata.get("source_type"),
                    "filename": metadata.get("filename"),
                    "path": metadata.get("path"),
                    "start_line": metadata.get("start_line"),
                    "end_line": metadata.get("end_line"),
                    "chunk_id": metadata.get("chunk_id"),
                    "distance": distance,
                    "score": hit["score"],
                }
            )
            context_lines.append(
                f"- (kind=code, source_type={metadata.get('source_type', 'code')}, score={hit['score']}, path={metadata.get('path')}, L{metadata.get('start_line')}-L{metadata.get('end_line')}, chunk_id={metadata.get('chunk_id', '')}) {document}"
            )

    return "\n".join(context_lines), citations
