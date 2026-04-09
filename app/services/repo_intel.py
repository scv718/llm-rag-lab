from __future__ import annotations

from functools import lru_cache
import json
import re
from pathlib import Path
from typing import Any


STRUCTURE_QUERY_HINTS = {
    "구조", "흐름", "연결", "관계", "역할", "아키텍처", "패키지",
    "전체", "프로젝트", "시스템", "주고받", "오가", "호출 순서",
    "flow", "flows", "structure", "architecture", "relationship",
    "relationships", "connect", "connected", "overview",
}

MANIFEST_FILES = ("pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "README.md", "README.MD")
CONFIG_GLOBS = ("application*.yml", "application*.yaml", "application*.properties")
CODE_GLOBS = (
    "*.java", "*.kt", "*.py", "*.js", "*.ts", "*.tsx", "*.jsx", "*.go",
    "*.rb", "*.php", "*.cs",
)

CODE_MARKERS = (
    "@RequestMapping", "@PostMapping", "@GetMapping",
    "ServerSocket", "MulticastSocket", "DatagramPacket", "RestClient",
    "RestTemplate", "sendData(", "sendRequestMsg(", "receive(", "TcpSender",
    "UdpSend", "Receiver", "Listener", "Queue", "heartbeat", "diagnosis",
)

CONFIG_INTEREST_TOKENS = ("port", "url", "host", "ip", "mode")
OUTBOUND_TOKENS = ("send", "sender", "client", "publish", "post", "restclient", "resttemplate")
INBOUND_TOKENS = ("receive", "receiver", "listener", "serversocket", "multicastsocket", "@requestmapping", "@postmapping")
TRANSFORM_TOKENS = ("parse", "parser", "encode", "decode", "queue", "poll", "handler")
ENTRY_PATH_TOKENS = (
    "main", "application", "bootstrap", "startup", "cli",
)
INPUT_TOKENS = (
    "controller", "route", "router", "endpoint", "handler", "listener", "receiver",
    "consumer", "subscriber", "webhook", "api", "requestmapping", "postmapping",
    "getmapping", "messagepattern", "serversocket", "multicastsocket",
)
PROCESS_TOKENS = (
    "service", "usecase", "processor", "orchestr", "workflow", "manager", "engine",
    "parse", "parser", "transform", "decode", "encode", "queue", "poll", "handler",
)
OUTPUT_TOKENS = (
    "sender", "client", "producer", "publisher", "gateway", "adapter", "proxy",
    "emit", "dispatch", "deliver", "forward", "restclient", "resttemplate", "send",
)
CONFIG_PATH_TOKENS = (
    "config", "setting", "properties", "yaml", "yml", "env", "profile",
)


def classify_question_type(question: str) -> str:
    lower_question = (question or "").lower()
    if any(token in lower_question for token in STRUCTURE_QUERY_HINTS):
        return "structure"
    return "general"


def should_build_repo_overview(question: str, repo_count: int) -> bool:
    if repo_count <= 0:
        return False
    return classify_question_type(question) == "structure"


def recommended_rerank_limit(question: str, repo_count: int, default_limit: int) -> int:
    if should_build_repo_overview(question, repo_count):
        return max(default_limit, min(24, default_limit + max(6, repo_count * 2)))
    return default_limit


def build_repo_overview_context(question: str, repos: list[dict]) -> tuple[str, list[dict]]:
    if not should_build_repo_overview(question, len(repos)):
        return "", []

    summaries = []
    citations = []
    for repo in repos:
        summary = load_repo_intel_artifact(repo) or summarize_repo(repo)
        if summary:
            summaries.append(summary)
            citations.append(
                {
                    "kind": "repo_summary",
                    "repo_id": repo_value(repo, "repo_id"),
                    "filename": repo_value(repo, "filename"),
                    "extract_path": repo_value(repo, "extract_path"),
                    "role": summary["role"],
                    "evidence_paths": summary["evidence_paths"],
                }
            )

    if not summaries:
        return "", []

    relation_lines, relation_citations = build_relation_lines(summaries)
    citations.extend(relation_citations)

    lines = ["[프로젝트 개요]"]
    for summary in summaries:
        lines.append(
            f"- repo={summary['display_name']}, role={summary['role']}, entry={summary['entry']}"
        )
        lines.append(
            f"  packages={summary['package_summary']}, roles={summary['role_summary']}"
        )
        lines.append(
            f"  config={summary['config_summary']}"
        )
        lines.append(
            f"  signals={summary['signal_summary']}"
        )

    if relation_lines:
        lines.append("[관계 요약]")
        lines.extend(f"- {line}" for line in relation_lines)

    return "\n".join(lines), citations


def summarize_repo(repo: dict) -> dict | None:
    extract_path = repo_value(repo, "extract_path")
    if not extract_path:
        return None

    summary = _summarize_repo_cached(
        extract_path=str(extract_path),
        filename=repo_value(repo, "filename") or "",
        repo_id=repo_value(repo, "repo_id") or "",
    )
    if summary:
        save_repo_intel_artifact(repo, summary)
    return summary


@lru_cache(maxsize=64)
def _summarize_repo_cached(extract_path: str, filename: str, repo_id: str) -> dict | None:
    repo = {
        "extract_path": extract_path,
        "filename": filename,
        "repo_id": repo_id,
    }

    root = Path(extract_path)
    if not root.exists():
        return None

    manifests = collect_manifest_files(root)
    configs = collect_config_files(root)
    code_files = collect_code_files(root)

    manifest_texts = [safe_read_text(path) for path in manifests]
    config_pairs = []
    for config_path in configs:
        config_pairs.extend(extract_config_pairs(config_path))

    code_signals = []
    for code_path in code_files:
        code_signals.extend(extract_code_signals(code_path))

    display_name = detect_display_name(repo, manifest_texts, root)
    signal_counts = count_repo_signals(code_files, config_pairs, code_signals)
    role = detect_role(signal_counts)
    entry = detect_entry_point(code_files, manifest_texts)
    config_summary = summarize_config_pairs(config_pairs)
    signal_summary = summarize_signals(code_signals)
    package_summary = summarize_packages(code_files, root)
    role_map = analyze_role_candidates(code_files, root, config_pairs, code_signals, manifests, configs)
    role_summary = summarize_role_map(role_map)
    evidence_paths = unique_paths(manifests + configs + code_files)

    return {
        "repo_id": repo_value(repo, "repo_id"),
        "display_name": display_name,
        "role": role,
        "entry": entry,
        "config_summary": config_summary,
        "signal_summary": signal_summary,
        "package_summary": package_summary,
        "role_summary": role_summary,
        "role_map": role_map,
        "config_pairs": config_pairs,
        "code_signals": code_signals,
        "signal_counts": signal_counts,
        "evidence_paths": evidence_paths,
    }


def collect_manifest_files(root: Path) -> list[Path]:
    found = []
    for name in MANIFEST_FILES:
        path = root / name
        if path.exists():
            found.append(path)
    return found[:6]


def collect_config_files(root: Path) -> list[Path]:
    found = []
    for pattern in CONFIG_GLOBS:
        found.extend(sorted(root.rglob(pattern)))
    return unique_path_objects(found)[:12]


def collect_code_files(root: Path) -> list[Path]:
    found = []
    for pattern in CODE_GLOBS:
        found.extend(sorted(root.rglob(pattern)))
    return unique_path_objects(found)[:80]


def safe_read_text(path: Path, limit: int = 12000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    return text[:limit]


def detect_display_name(repo: dict, manifest_texts: list[str], root: Path) -> str:
    filename = repo_value(repo, "filename") or repo_value(repo, "repo_id") or root.name
    manifest_blob = "\n".join(manifest_texts)

    for pattern in (r"<name>([^<]+)</name>", r"<artifactId>([^<]+)</artifactId>"):
        match = re.search(pattern, manifest_blob)
        if match:
            value = match.group(1).strip()
            if value and "spring-boot-starter-parent" not in value:
                return value
    return filename


def repo_value(repo: Any, key: str, default: Any = None) -> Any:
    if repo is None:
        return default
    if isinstance(repo, dict):
        return repo.get(key, default)
    try:
        return repo[key]
    except Exception:
        return default


def count_repo_signals(
    code_files: list[Path],
    config_pairs: list[tuple[str, str, str]],
    code_signals: list[tuple[str, int, str]],
) -> dict[str, int]:
    combined = " ".join(
        [path.as_posix().lower() for path in code_files]
        + [f"{key} {value}".lower() for _, key, value in config_pairs]
        + [text.lower() for _, _, text in code_signals]
    )

    outbound = sum(combined.count(token) for token in OUTBOUND_TOKENS)
    inbound = sum(combined.count(token) for token in INBOUND_TOKENS)
    transform = sum(combined.count(token) for token in TRANSFORM_TOKENS)
    config_port = sum("port" in key.lower() for _, key, _ in config_pairs)
    config_url = sum("url" in key.lower() for _, key, _ in config_pairs)
    return {
        "outbound": outbound,
        "inbound": inbound,
        "transform": transform,
        "config_port": config_port,
        "config_url": config_url,
    }


def detect_role(signal_counts: dict[str, int]) -> str:
    outbound = signal_counts["outbound"]
    inbound = signal_counts["inbound"]
    transform = signal_counts["transform"]

    if outbound > 0 and inbound > 0:
        if transform > 0:
            return "relay"
        return "gateway"
    if outbound > 0 and inbound == 0:
        return "producer"
    if inbound > 0 and outbound == 0:
        return "receiver"
    if transform > 0:
        return "processor"
    return "application"


def detect_entry_point(code_files: list[Path], manifest_texts: list[str]) -> str:
    manifest_blob = "\n".join(manifest_texts)
    main_class = re.search(r"<mainClass>([^<]+)</mainClass>", manifest_blob)
    if main_class:
        return main_class.group(1).strip()

    for path in code_files:
        name = path.name
        if name.endswith(("Main.java", "Application.java")):
            return name
    return "-"


def extract_config_pairs(path: Path) -> list[tuple[str, str, str]]:
    text = safe_read_text(path)
    if not text:
        return []

    pairs = []
    stack: list[str] = []
    for line in text.splitlines():
        raw = line.rstrip()
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if "=" in stripped and not stripped.startswith("-"):
            key, value = stripped.split("=", 1)
            if any(token in key.lower() for token in CONFIG_INTEREST_TOKENS):
                pairs.append((path.name, key.strip(), value.strip()))
            continue

        yaml_match = re.match(r"^(\s*)([A-Za-z0-9_.\-]+)\s*:\s*(.*)$", raw)
        if not yaml_match:
            continue

        indent = len(yaml_match.group(1))
        key = yaml_match.group(2).strip()
        value = yaml_match.group(3).strip()
        level = indent // 2
        while len(stack) > level:
            stack.pop()
        if len(stack) == level:
            stack.append(key)
        else:
            stack = stack[:level] + [key]

        full_key = ".".join(stack)
        if value and any(token in full_key.lower() for token in CONFIG_INTEREST_TOKENS):
            pairs.append((path.name, full_key, value))

    return pairs[:40]


def extract_code_signals(path: Path) -> list[tuple[str, int, str]]:
    text = safe_read_text(path)
    if not text:
        return []

    signals = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if any(marker in stripped for marker in CODE_MARKERS):
            signals.append((path.name, line_no, stripped[:180]))
        if len(signals) >= 12:
            break
    return signals


def summarize_config_pairs(pairs: list[tuple[str, str, str]]) -> str:
    if not pairs:
        return "-"

    parts = []
    for file_name, key, value in pairs[:6]:
        parts.append(f"{file_name}:{key}={value}")
    return " | ".join(parts)


def summarize_signals(signals: list[tuple[str, int, str]]) -> str:
    if not signals:
        return "-"

    parts = []
    for file_name, line_no, text in signals[:6]:
        parts.append(f"{file_name}:{line_no}:{text}")
    return " | ".join(parts)


def summarize_packages(code_files: list[Path], root: Path) -> str:
    packages = []
    seen = set()
    for path in code_files:
        try:
            relative_parent = path.relative_to(root).parent.as_posix()
        except ValueError:
            relative_parent = path.parent.as_posix()
        if not relative_parent or relative_parent == ".":
            continue
        if relative_parent in seen:
            continue
        seen.add(relative_parent)
        packages.append(relative_parent)
    return " | ".join(packages[:6]) if packages else "-"


def analyze_role_candidates(
    code_files: list[Path],
    root: Path,
    config_pairs: list[tuple[str, str, str]],
    code_signals: list[tuple[str, int, str]],
    manifests: list[Path],
    configs: list[Path],
) -> dict[str, list[str]]:
    signal_map: dict[str, list[str]] = {}
    for file_name, _, text in code_signals:
        signal_map.setdefault(file_name, []).append(text.lower())

    scored: dict[str, dict[str, int]] = {}
    for path in code_files:
        rel = safe_relative_path(path, root)
        bucket = scored.setdefault(rel, {"entry": 0, "input": 0, "process": 0, "output": 0})
        path_text = rel.lower()
        signal_text = " ".join(signal_map.get(path.name, []))

        bucket["entry"] += score_tokens(path_text, ENTRY_PATH_TOKENS)
        bucket["entry"] += score_tokens(signal_text, ("public static void main", "springapplication.run", "fastapi(", "express()", "uvicorn.run"))

        bucket["input"] += score_tokens(path_text, INPUT_TOKENS)
        bucket["input"] += score_tokens(signal_text, ("@requestmapping", "@postmapping", "@getmapping", "router.", "app.", "serversocket", "multicastsocket"))

        bucket["process"] += score_tokens(path_text, PROCESS_TOKENS)
        bucket["process"] += score_tokens(signal_text, ("queue", "handler", "process", "transform", "parser", "decode", "encode"))

        bucket["output"] += score_tokens(path_text, OUTPUT_TOKENS)
        bucket["output"] += score_tokens(signal_text, ("restclient", "resttemplate", "senddata(", "sendrequestmsg(", "publish", "forward", "dispatch"))

    config_surfaces = []
    for path in manifests + configs:
        config_surfaces.append(safe_relative_path(path, root))
    for file_name, key, value in config_pairs[:12]:
        config_surfaces.append(f"{file_name}:{key}={value}")

    return {
        "entry": top_role_candidates(scored, "entry", min_score=2),
        "input": top_role_candidates(scored, "input", min_score=2),
        "process": top_role_candidates(scored, "process", min_score=2),
        "output": top_role_candidates(scored, "output", min_score=2),
        "config": unique_texts(config_surfaces)[:8],
    }


def safe_relative_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def score_tokens(text: str, tokens: tuple[str, ...]) -> int:
    return sum(text.count(token) for token in tokens)


def top_role_candidates(scored: dict[str, dict[str, int]], role_name: str, limit: int = 4, min_score: int = 1) -> list[str]:
    ranked = sorted(
        ((path, scores[role_name]) for path, scores in scored.items() if scores[role_name] >= min_score),
        key=lambda item: (-item[1], item[0]),
    )
    return [path for path, _ in ranked[:limit]]


def unique_texts(items: list[str]) -> list[str]:
    unique = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def summarize_role_map(role_map: dict[str, list[str]]) -> str:
    parts = []
    for role_name in ("entry", "input", "process", "output", "config"):
        values = role_map.get(role_name) or []
        if not values:
            continue
        parts.append(f"{role_name}={', '.join(values[:3])}")
    return " | ".join(parts) if parts else "-"


def build_relation_lines(summaries: list[dict]) -> tuple[list[str], list[dict]]:
    relation_lines = []
    citations = []
    for src in summaries:
        for dst in summaries:
            if src["repo_id"] == dst["repo_id"]:
                continue

            relation = detect_relation(src, dst)
            if not relation:
                continue

            line = f"{src['display_name']} -> {dst['display_name']}: {relation['description']}"
            if line in relation_lines:
                continue
            relation_lines.append(line)
            citations.append(
                {
                    "kind": "repo_relation",
                    "from_repo_id": src["repo_id"],
                    "to_repo_id": dst["repo_id"],
                    "description": relation["description"],
                    "evidence_paths": relation["evidence_paths"],
                }
            )

    return relation_lines[:8], citations[:8]


def detect_relation(src: dict, dst: dict) -> dict | None:
    src_counts = src["signal_counts"]
    dst_counts = dst["signal_counts"]
    src_config = " ".join(f"{key} {value}".lower() for _, key, value in src["config_pairs"])
    dst_config = " ".join(f"{key} {value}".lower() for _, key, value in dst["config_pairs"])
    src_signals = " ".join(text.lower() for _, _, text in src["code_signals"])
    dst_signals = " ".join(text.lower() for _, _, text in dst["code_signals"])
    evidence_paths = src["evidence_paths"][:3] + dst["evidence_paths"][:3]

    if src_counts["outbound"] > 0 and dst_counts["inbound"] > 0:
        if src_counts["transform"] == 0 or src["role"] == "producer":
            return {
                "description": "상류 송신 코드와 하류 수신/처리 코드가 맞물려 데이터가 다음 서비스로 유입되는 구조로 보임",
                "evidence_paths": evidence_paths,
            }

    if src_counts["outbound"] > 0 and src_counts["inbound"] > 0 and dst_counts["inbound"] > 0:
        if any(token in src_signals for token in ("udpsend", "senddata(", "restclient", "resttemplate", "client")):
            return {
                "description": "중계 서비스가 수신 후 재전송 또는 보고 호출을 통해 다음 서비스와 연결되는 구조로 보임",
                "evidence_paths": evidence_paths,
            }

    if "alarm-url" in src_config and "medalarmreport" in dst_signals:
        return {
            "description": "한 서비스의 알람 보고 URL 설정과 다른 서비스의 수신 API가 맞물려 보고 경로가 형성된 것으로 보임",
            "evidence_paths": evidence_paths,
        }

    if "/v1/request" in src_config and "@requestmapping(\"/v1/request\")" in dst_signals:
        return {
            "description": "한 서비스의 외부 호출 URL 설정과 다른 서비스의 요청 API가 맞물려 조회/제어 경로가 형성된 것으로 보임",
            "evidence_paths": evidence_paths,
        }

    if src_counts["outbound"] > 0 and src_counts["config_port"] > 0 and dst_counts["inbound"] > 0 and dst_counts["config_port"] > 0:
        if any(token in src_signals for token in ("sender", "send")) and any(token in dst_signals for token in ("receiver", "listener", "serversocket", "multicastsocket")):
            return {
                "description": "송신/수신 구성과 포트 설정이 함께 보여 서비스 간 데이터 전달 경로가 있는 것으로 보임",
                "evidence_paths": evidence_paths,
            }

    return None


def unique_paths(paths: list[Path]) -> list[str]:
    unique = []
    seen = set()
    for path in paths:
        key = path.as_posix()
        if key in seen:
            continue
        seen.add(key)
        unique.append(key)
    return unique


def unique_path_objects(paths: list[Path]) -> list[Path]:
    unique = []
    seen = set()
    for path in paths:
        key = path.as_posix()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def repo_intel_artifact_path(repo: dict | None) -> Path | None:
    extract_path = repo_value(repo, "extract_path")
    if not extract_path:
        return None
    return Path(extract_path) / ".repo_intel.json"


def load_repo_intel_artifact(repo: dict | None) -> dict | None:
    path = repo_intel_artifact_path(repo)
    if not path or not path.exists():
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_repo_intel_artifact(repo: dict | None, summary: dict) -> None:
    path = repo_intel_artifact_path(repo)
    if not path:
        return

    try:
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return


def build_and_store_repo_intel_artifact(repo: dict | None) -> dict | None:
    return summarize_repo(repo)
