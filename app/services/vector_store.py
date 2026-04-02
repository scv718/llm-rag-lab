# app/services/vector_store.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import chromadb
from chromadb.config import Settings


class VectorStore:
    """
    Chroma 기반 로컬 벡터 스토어.
    - persist_directory 지정 시 서버 재시작 후에도 데이터 유지
    """
    def __init__(self, persist_directory: str = "chroma_db", collection_name: str = "docs"):
        self._client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(name=collection_name)

    def upsert(
        self,
        *,
        ids: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
        documents: List[str],
    ) -> None:
        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents,
        )

    def query(
        self,
        *,
        query_embedding: List[float],
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        반환 형태를 쓰기 편하게 평탄화해서 돌려준다.
        """
        res = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["metadatas", "documents", "distances"],
        )

        # Chroma는 batch 형태(리스트 안 리스트)로 반환함
        metadatas = (res.get("metadatas") or [[]])[0]
        documents = (res.get("documents") or [[]])[0]
        distances = (res.get("distances") or [[]])[0]

        out: List[Dict[str, Any]] = []
        for m, d, dist in zip(metadatas, documents, distances):
            out.append(
                {
                    "metadata": m or {},
                    "document": d or "",
                    "distance": float(dist),
                    # cosine 거리/유사도 설정은 컬렉션 설정에 따라 다르지만
                    # MVP에서는 distance를 그대로 노출(낮을수록 가깝다고 보는 경우가 흔함)
                }
            )
        return out

    def reset(self) -> None:
        # 전체 삭제(개발용)
        self._client.delete_collection(self._collection.name)
        self._collection = self._client.get_or_create_collection(name=self._collection.name)