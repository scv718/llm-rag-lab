# app/services/embeddings.py
from __future__ import annotations
from typing import List, Sequence, Optional

EMBED_MODEL = "gemini-embedding-001"  # ✅ text-embedding-004 대신

def _batched(seq: Sequence[str], batch_size: int):
    for i in range(0, len(seq), batch_size):
        yield seq[i:i + batch_size]

def _to_vec(e) -> List[float]:
    # google-genai 응답 형태 버전차 대응
    if hasattr(e, "values"):
        return list(e.values)
    if hasattr(e, "embedding") and hasattr(e.embedding, "values"):
        return list(e.embedding.values)
    raise RuntimeError("Unknown embedding response shape")

def embed_documents(client, texts: List[str], title: Optional[str] = None, batch_size: int = 100) -> List[List[float]]:
    """
    - v1beta embedContent는 1 batch 당 최대 100개 제한
    - 모델은 gemini-embedding-001 사용
    """
    if not texts:
        return []

    batch_size = max(1, min(int(batch_size), 100))
    vectors: List[List[float]] = []

    for batch in _batched(texts, batch_size):
        resp = client.models.embed_content(
            model=EMBED_MODEL,
            contents=batch,
            # 필요하면 config로 output_dimensionality 지정 가능(아래 참고)
        )
        vectors.extend(_to_vec(e) for e in resp.embeddings)

    return vectors

def embed_query(client, text: str) -> List[float]:
    resp = client.models.embed_content(
        model=EMBED_MODEL,
        contents=[text],
    )
    return _to_vec(resp.embeddings[0])