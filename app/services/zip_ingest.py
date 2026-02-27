# app/services/zip_ingest.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
import os
import zipfile
import hashlib


TEXT_EXTS = {
    ".java", ".py", ".js", ".ts", ".jsx", ".tsx",
    ".md", ".txt",
    ".yml", ".yaml",
    ".json", ".xml",
    ".properties", ".gradle", ".sql",
    ".sh", ".bat", ".ps1",
    ".ini", ".cfg",
}

# 업로드 zip 내부에서 흔히 섞이는 것들 제외
SKIP_DIR_NAMES = {".git", ".idea", ".vscode", "__pycache__", "node_modules", "dist", "build", "target", "venv"}
SKIP_FILE_NAMES = {".env", ".env.local", ".env.dev", ".env.prod"}  # 키 유출 방지


@dataclass(frozen=True)
class CodeChunk:
    chunk_id: str
    repo_id: str
    path: str
    lang: str
    start_line: int
    end_line: int
    text: str


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _is_within_dir(base: Path, target: Path) -> bool:
    # Zip Slip 방어: base 밖으로 나가면 False
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except Exception:
        return False


def safe_extract_zip(
    *,
    zip_path: Path,
    extract_dir: Path,
    max_files: int = 5000,
    max_total_uncompressed_bytes: int = 200 * 1024 * 1024,  # 200MB
) -> Tuple[int, int]:
    """
    안전한 압축 해제:
    - Zip Slip 방어
    - 파일 개수 제한
    - 해제 총량 제한
    """
    extract_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    count = 0

    with zipfile.ZipFile(zip_path, "r") as zf:
        infos = zf.infolist()
        if len(infos) > max_files:
            raise ValueError(f"ZIP contains too many entries: {len(infos)} > {max_files}")

        for info in infos:
            # 디렉토리 엔트리 스킵
            if info.is_dir():
                continue

            # 총 해제 바이트 제한(압축폭탄 방어의 1차)
            total += int(info.file_size or 0)
            if total > max_total_uncompressed_bytes:
                raise ValueError("ZIP uncompressed size limit exceeded")

            # 경로 정규화 + Zip Slip 방어
            rel = Path(info.filename)
            # zip 내부 경로는 POSIX 스타일이 많음. Path가 알아서 처리하긴 하지만, 절대경로/드라이브 제거 방어
            rel = Path(*[p for p in rel.parts if p not in ("", ".", "..")])
            out_path = extract_dir / rel

            if not _is_within_dir(extract_dir, out_path):
                raise ValueError("Blocked Zip Slip attempt")

            out_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, open(out_path, "wb") as dst:
                dst.write(src.read())

            count += 1

    return count, total


def _guess_lang(path: str) -> str:
    p = Path(path)
    if p.name == "Dockerfile":
        return "dockerfile"
    ext = p.suffix.lower()
    if ext == ".py":
        return "python"
    if ext == ".java":
        return "java"
    if ext in (".js", ".jsx"):
        return "javascript"
    if ext in (".ts", ".tsx"):
        return "typescript"
    if ext in (".yml", ".yaml"):
        return "yaml"
    if ext == ".json":
        return "json"
    if ext == ".xml":
        return "xml"
    if ext == ".md":
        return "markdown"
    if ext == ".sql":
        return "sql"
    return ext.lstrip(".") or "text"


def iter_source_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_dir():
            continue

        # 스킵 디렉토리 포함이면 제외
        if any(part in SKIP_DIR_NAMES for part in p.parts):
            continue

        if p.name in SKIP_FILE_NAMES:
            continue

        if p.name == "Dockerfile":
            yield p
            continue

        ext = p.suffix.lower()
        if ext in TEXT_EXTS:
            yield p


def read_text_best_effort(path: Path, max_bytes: int = 2 * 1024 * 1024) -> str:
    """
    텍스트 파일 best-effort 읽기
    - 너무 큰 파일은 상한으로 컷
    - 인코딩은 utf-8 우선, 실패 시 cp949, latin-1 순으로 시도
    """
    raw = path.read_bytes()
    if len(raw) > max_bytes:
        raw = raw[:max_bytes]

    for enc in ("utf-8", "utf-8-sig", "cp949", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    # 최후: 에러 무시
    return raw.decode("utf-8", errors="ignore")


def chunk_code_by_lines(
    *,
    repo_id: str,
    rel_path: str,
    text: str,
    lines_per_chunk: int = 250,
    overlap: int = 40,
) -> List[CodeChunk]:
    if lines_per_chunk <= 0:
        raise ValueError("lines_per_chunk must be > 0")
    if overlap < 0 or overlap >= lines_per_chunk:
        raise ValueError("overlap must be >=0 and < lines_per_chunk")

    lines = text.splitlines()
    if not lines:
        return []

    lang = _guess_lang(rel_path)

    chunks: List[CodeChunk] = []
    step = lines_per_chunk - overlap
    start = 0
    idx = 0

    while start < len(lines):
        end = min(start + lines_per_chunk, len(lines))
        piece_lines = lines[start:end]
        piece = "\n".join(piece_lines).strip()

        if piece:
            chunk_id = f"{repo_id}:{rel_path}:L{start+1}-L{end}:{idx:03d}"
            chunks.append(
                CodeChunk(
                    chunk_id=chunk_id,
                    repo_id=repo_id,
                    path=rel_path,
                    lang=lang,
                    start_line=start + 1,
                    end_line=end,
                    text=piece,
                )
            )
            idx += 1

        start += step

    return chunks