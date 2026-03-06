import os
import requests
from dataclasses import dataclass
from typing import Any


RAG_API_URL = os.environ.get("RAG_API_URL", "http://127.0.0.1:8000/rag/ask")
USE_REAL_API = os.environ.get("USE_REAL_API", "false").lower() == "true"


@dataclass
class RagResult:
    answer_markdown: str
    evidence: list
    artifacts: list

    @staticmethod
    def from_any(payload: Any):

        if isinstance(payload, str):
            return RagResult(payload, [], [])

        if isinstance(payload, dict):

            ans = payload.get("answer_markdown") or payload.get("answer") or payload.get("text") or ""
            ev = payload.get("evidence") or payload.get("citations") or []
            ar = payload.get("artifacts") or []

            if not isinstance(ev, list):
                ev = []

            if not isinstance(ar, list):
                ar = []

            return RagResult(ans, ev, ar)

        return RagResult(str(payload), [], [])


def call_rag_api(question: str, top_k: int):

    if not USE_REAL_API:

        demo = {
            "answer_markdown": f"### (DEMO)\n질문: `{question}`",
            "evidence": [],
            "artifacts": [],
        }

        return RagResult.from_any(demo)

    payload = {
        "question": question,
        "top_k": int(top_k),
    }

    r = requests.post(RAG_API_URL, json=payload, timeout=180)
    r.raise_for_status()

    try:
        data = r.json()
    except Exception:
        data = r.text

    return RagResult.from_any(data)