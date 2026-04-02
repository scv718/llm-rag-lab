# app/services/chunking.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List
import re


@dataclass(frozen=True)
class TextChunk:
    chunk_id: str          # e.g. "doc-0001_p003_c012"
    page: int              # 1-based page number
    chunk_index: int       # 0-based index within that page
    text: str              # chunk text
    char_start: int        # start offset within the page text
    char_end: int          # end offset within the page text


def _normalize_text(text: str) -> str:
    # PDF 추출 텍스트는 공백/줄바꿈이 지저분한 경우가 많아서 최소 정리만 한다.
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text_by_chars(
    *,
    doc_id: str,
    page: int,
    text: str,
    chunk_size: int = 900,     # 글자 기준 (초기 MVP용)
    overlap: int = 150,        # 글자 기준 overlap
) -> List[TextChunk]:
    """
    페이지 텍스트를 '글자수 기준'으로 잘라 chunk를 만든다.
    - 추후 토큰 기반 chunker로 교체 가능
    - page/offset/idx를 메타데이터로 보존해서 citation에 활용
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if overlap < 0:
        raise ValueError("overlap must be >= 0")
    if overlap >= chunk_size:
        raise ValueError("overlap must be < chunk_size")

    normalized = _normalize_text(text)
    if not normalized:
        return []

    chunks: List[TextChunk] = []
    step = chunk_size - overlap
    start = 0
    idx = 0

    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        piece = normalized[start:end].strip()

        if piece:
            chunk_id = f"{doc_id}_p{page:03d}_c{idx:03d}"
            chunks.append(
                TextChunk(
                    chunk_id=chunk_id,
                    page=page,
                    chunk_index=idx,
                    text=piece,
                    char_start=start,
                    char_end=end,
                )
            )
            idx += 1

        start += step

    return chunks