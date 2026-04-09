import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path


CODE_EXTENSIONS = {
    ".java", ".kt", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".xml", ".yml", ".yaml", ".properties", ".sql",
    ".cpp", ".c", ".cs", ".go", ".rb", ".php",
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
        "은", "는", "의", "에서", "으로", "로", "와", "과",
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
    rg_results = _keyword_search_in_repo_with_rg(repo_dir=repo_dir, keywords=keywords, limit=limit)
    if rg_results is not None:
        return rg_results
    return _keyword_search_in_repo_python(repo_dir=repo_dir, keywords=keywords, limit=limit)


def _keyword_search_in_repo_with_rg(repo_dir: Path, keywords: list[str], limit: int = 200) -> list[dict] | None:
    if not repo_dir.exists() or not keywords:
        return []

    glob_args = []
    for ext in CODE_EXTENSIONS:
        glob_args.extend(["-g", f"*{ext}"])

    pattern = "|".join(re.escape(keyword) for keyword in keywords if keyword)
    if not pattern:
        return []

    try:
        proc = subprocess.run(
            [
                "rg",
                "--line-number",
                "--column",
                "--with-filename",
                "--color",
                "never",
                "--no-heading",
                "--smart-case",
                "--max-count",
                str(limit),
                *glob_args,
                pattern,
                str(repo_dir),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return None

    if proc.returncode not in (0, 1):
        return None

    results = []
    seen = set()
    results.extend(_collect_path_hits(repo_dir=repo_dir, keywords=keywords, limit=limit, seen=seen))
    if len(results) >= limit:
        return results[:limit]

    for line in proc.stdout.splitlines():
        parts = line.split(":", 3)
        if len(parts) != 4:
            continue
        abs_path, line_no_text, _column_text, line_text = parts
        file_path = Path(abs_path)
        try:
            rel_path = str(file_path.relative_to(repo_dir)).replace("\\", "/")
        except Exception:
            continue

        try:
            line_no = int(line_no_text)
        except ValueError:
            continue

        matched_keywords = [
            keyword for keyword in keywords
            if keyword and keyword.lower() in line_text.lower()
        ]
        if not matched_keywords:
            continue

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
            break

    return results


def _keyword_search_in_repo_python(repo_dir: Path, keywords: list[str], limit: int = 200) -> list[dict]:
    results = []
    seen = set()

    if not repo_dir.exists() or not keywords:
        return results

    results.extend(_collect_path_hits(repo_dir=repo_dir, keywords=keywords, limit=limit, seen=seen))
    if len(results) >= limit:
        return results[:limit]

    for root, _, files in os.walk(repo_dir):
        for file_name in files:
            ext = Path(file_name).suffix.lower()
            if ext not in CODE_EXTENSIONS:
                continue

            file_path = Path(root) / file_name
            rel_path = str(file_path.relative_to(repo_dir)).replace("\\", "/")

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


def _collect_path_hits(repo_dir: Path, keywords: list[str], limit: int, seen: set) -> list[dict]:
    path_index = _build_repo_path_index(repo_dir)
    results = []
    candidate_paths = _candidate_paths_for_keywords(path_index, keywords)
    if not candidate_paths:
        candidate_paths = _list_repo_code_paths(repo_dir)

    for rel_path in candidate_paths:
        matched_path_keywords = _match_keywords_against_path(rel_path, keywords)
        if not matched_path_keywords:
            continue
        dedup_key = ("path", rel_path)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        results.append(
            {
                "source": "path",
                "path": rel_path,
                "line": 0,
                "text": rel_path,
                "matched_keywords": matched_path_keywords,
            }
        )
        if len(results) >= limit:
            break
    return results


def _list_repo_code_paths(repo_dir: Path) -> tuple[str, ...]:
    repo_dir = repo_dir.resolve()
    if not repo_dir.exists():
        return ()

    signature = _repo_path_cache_signature(repo_dir)
    return _list_repo_code_paths_cached(str(repo_dir), signature)


def _repo_path_cache_signature(repo_dir: Path) -> tuple[str, int]:
    stat = repo_dir.stat()
    return str(repo_dir), stat.st_mtime_ns


@lru_cache(maxsize=64)
def _list_repo_code_paths_cached(repo_dir_str: str, _signature: tuple[str, int]) -> tuple[str, ...]:
    repo_dir = Path(repo_dir_str)
    rg_paths = _list_repo_code_paths_with_rg(repo_dir)
    if rg_paths is not None:
        return tuple(rg_paths)
    return tuple(_list_repo_code_paths_with_python(repo_dir))


def _list_repo_code_paths_with_rg(repo_dir: Path) -> list[str] | None:
    glob_args = []
    for ext in CODE_EXTENSIONS:
        glob_args.extend(["-g", f"*{ext}"])

    try:
        proc = subprocess.run(
            [
                "rg",
                "--files",
                *glob_args,
                str(repo_dir),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return None

    if proc.returncode != 0:
        return None

    paths = []
    for line in proc.stdout.splitlines():
        rel_path = _normalize_repo_relative_path(repo_dir, line)
        if rel_path:
            paths.append(rel_path)
    return paths


def _list_repo_code_paths_with_python(repo_dir: Path) -> list[str]:
    paths = []
    for root, _, files in os.walk(repo_dir):
        for file_name in files:
            ext = Path(file_name).suffix.lower()
            if ext not in CODE_EXTENSIONS:
                continue
            rel_path = str((Path(root) / file_name).relative_to(repo_dir)).replace("\\", "/")
            paths.append(rel_path)
    return paths


def _normalize_repo_relative_path(repo_dir: Path, raw_path: str) -> str | None:
    raw_path = raw_path.strip()
    if not raw_path:
        return None

    path = Path(raw_path)
    if path.is_absolute():
        try:
            return str(path.relative_to(repo_dir)).replace("\\", "/")
        except Exception:
            return None
    return raw_path.replace("\\", "/")


def _build_repo_path_index(repo_dir: Path) -> dict[str, tuple[str, ...]]:
    repo_dir = repo_dir.resolve()
    if not repo_dir.exists():
        return {}

    signature = _repo_path_cache_signature(repo_dir)
    return _build_repo_path_index_cached(str(repo_dir), signature)


@lru_cache(maxsize=64)
def _build_repo_path_index_cached(repo_dir_str: str, signature: tuple[str, int]) -> dict[str, tuple[str, ...]]:
    index: dict[str, list[str]] = {}
    for rel_path in _list_repo_code_paths_cached(repo_dir_str, signature):
        for token in _path_search_tokens(rel_path):
            bucket = index.setdefault(token, [])
            if not bucket or bucket[-1] != rel_path:
                bucket.append(rel_path)
    return {token: tuple(paths) for token, paths in index.items()}


def _candidate_paths_for_keywords(path_index: dict[str, tuple[str, ...]], keywords: list[str]) -> list[str]:
    candidates = []
    seen = set()

    for keyword in keywords:
        for token in _keyword_search_tokens(keyword):
            for rel_path in path_index.get(token, ()):
                if rel_path in seen:
                    continue
                seen.add(rel_path)
                candidates.append(rel_path)
    return candidates


def _match_keywords_against_path(rel_path: str, keywords: list[str]) -> list[str]:
    lower_path = rel_path.lower()
    path_tokens = _path_search_tokens(rel_path)
    matched = []
    for keyword in keywords:
        if not keyword:
            continue
        lower_keyword = keyword.lower()
        keyword_tokens = _keyword_search_tokens(keyword)
        if lower_keyword in lower_path or keyword_tokens.issubset(path_tokens):
            matched.append(keyword)
    return matched


def _keyword_search_tokens(keyword: str) -> set[str]:
    if not keyword:
        return set()

    raw = keyword.strip().replace("\\", "/")
    tokens = set()
    for part in re.split(r"[/.]+", raw):
        tokens.update(_identifier_tokens(part))

    compact = re.sub(r"[^A-Za-z0-9]", "", raw)
    if compact:
        tokens.add(compact.lower())
    return {token for token in tokens if len(token) >= 2}


def _path_search_tokens(rel_path: str) -> set[str]:
    tokens = set()
    normalized = rel_path.replace("\\", "/")
    for part in re.split(r"[/.]+", normalized):
        tokens.update(_identifier_tokens(part))
    compact = re.sub(r"[^A-Za-z0-9]", "", normalized)
    if compact:
        tokens.add(compact.lower())
    return {token for token in tokens if len(token) >= 2}


def _identifier_tokens(value: str) -> set[str]:
    if not value:
        return set()

    normalized = re.sub(r"[_\-]+", " ", value)
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", normalized)
    normalized = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", normalized)
    pieces = [piece.lower() for piece in re.split(r"[^A-Za-z0-9]+|\s+", normalized) if piece]

    tokens = set(pieces)
    compact = "".join(pieces)
    if compact:
        tokens.add(compact)
    return tokens


def merge_search_results(keyword_hits: list[dict], vector_hits: list[dict]) -> list[dict]:
    merged = []
    seen_keyword_lines = set()
    content_paths = set()

    for hit in keyword_hits:
        if hit["source"] == "path":
            continue
        merged.append(hit)
        seen_keyword_lines.add((hit["path"], hit["line"]))
        content_paths.add(hit["path"])

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
            if path:
                content_paths.add(path)

    for hit in keyword_hits:
        if hit["source"] != "path":
            continue
        if hit["path"] in content_paths:
            continue
        merged.append(hit)

    return merged
