# app/services/embeddings.py
from __future__ import annotations

from typing import List
from google import genai
from google.genai import types


EMBED_MODEL = "gemini-embedding-001"  # 공식 문서 예시 :contentReference[oaicite:1]{index=1}


def embed_documents(client: genai.Client, texts: List[str], title: str) -> List[List[float]]:
    """
    문서(코퍼스)용 임베딩: RETRIEVAL_DOCUMENT
    - title을 주면 검색 품질에 도움이 된다는 가이드가 있음 :contentReference[oaicite:2]{index=2}
    """
    resp = client.models.embed_content(
        model=EMBED_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            title=title,
        ),
    )
    return [e.values for e in resp.embeddings]


def embed_query(client: genai.Client, query: str) -> List[float]:
    """
    질의용 임베딩: RETRIEVAL_QUERY :contentReference[oaicite:3]{index=3}
    """
    resp = client.models.embed_content(
        model=EMBED_MODEL,
        contents=query,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
    )
    return resp.embeddings[0].values