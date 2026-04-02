# app/services/embeddings.py

from __future__ import annotations
from typing import List
from sentence_transformers import SentenceTransformer


# 로컬 임베딩 모델
MODEL_NAME = "BAAI/bge-small-en-v1.5"

# 모델 로드 (앱 시작 시 1번만 로드)
_model = SentenceTransformer(
    MODEL_NAME,
    device="cuda"   # GPU 있으면 사용, 없으면 자동 CPU
)


def embed_documents(texts: List[str]) -> List[List[float]]:
    """
    문서 여러개 embedding
    """
    if not texts:
        return []

    vectors = _model.encode(
        texts,
        normalize_embeddings=True
    )

    return vectors.tolist()


def embed_query(text: str) -> List[float]:
    """
    검색 query embedding
    """
    vec = _model.encode(
        [text],
        normalize_embeddings=True
    )

    return vec[0].tolist()