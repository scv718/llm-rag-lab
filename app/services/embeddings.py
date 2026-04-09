# app/services/embeddings.py

from __future__ import annotations
import os
from typing import List
from sentence_transformers import SentenceTransformer


MODEL_NAME = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
DEVICE = os.getenv("EMBEDDING_DEVICE", "cuda")
_model: SentenceTransformer | None = None


def resolve_embedding_device() -> str:
    requested = (DEVICE or "cuda").strip().lower()
    if requested != "cuda":
        return requested

    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass

    return "cpu"


def get_embedding_model() -> SentenceTransformer:
    global _model
    if _model is None:
        device = resolve_embedding_device()
        try:
            _model = SentenceTransformer(
                MODEL_NAME,
                device=device,
            )
        except Exception as exc:
            message = str(exc)
            if "upgrade torch to at least v2.6" in message or "CVE-2025-32434" in message:
                raise RuntimeError(
                    "임베딩 모델 로딩에 실패했습니다. 현재 설치된 torch 버전이 너무 낮습니다. "
                    "Windows 가상환경에서 `pip install --upgrade torch torchvision torchaudio`로 "
                    "torch 2.6 이상으로 올린 뒤 서버를 다시 시작하세요."
                ) from exc
            if "Torch not compiled with CUDA enabled" in message:
                raise RuntimeError(
                    "임베딩 모델 로딩에 실패했습니다. 현재 torch는 CPU 빌드인데 "
                    "`EMBEDDING_DEVICE=cuda`로 잡혀 있습니다. "
                    "`.env`에서 `EMBEDDING_DEVICE=cpu`로 바꾸거나 CUDA 지원 torch를 설치하세요."
                ) from exc
            raise RuntimeError(
                f"임베딩 모델 `{MODEL_NAME}` 로딩에 실패했습니다: {exc}"
            ) from exc
    return _model


def embed_documents(texts: List[str]) -> List[List[float]]:
    """
    문서 여러개 embedding
    """
    if not texts:
        return []

    vectors = get_embedding_model().encode(
        texts,
        normalize_embeddings=True
    )

    return vectors.tolist()


def embed_query(text: str) -> List[float]:
    """
    검색 query embedding
    """
    vec = get_embedding_model().encode(
        [text],
        normalize_embeddings=True
    )

    return vec[0].tolist()
