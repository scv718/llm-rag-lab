import os
import json
import requests
from dataclasses import dataclass
from typing import Any


RAG_API_URL = os.environ.get("RAG_API_URL", "http://127.0.0.1:8000/rag/ask")
USE_REAL_API = os.environ.get("USE_REAL_API", "true").lower() == "true"


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

            debug_artifacts = []
            for label, key in (
                ("ranking_debug", "ranking_debug"),
                ("target", "target"),
                ("keywords", "keywords"),
                ("symbol_hints", "symbol_hints"),
            ):
                value = payload.get(key)
                if value in (None, [], {}, ""):
                    continue
                debug_artifacts.append(
                    {
                        "label": label,
                        "content": json.dumps(value, ensure_ascii=False, indent=2),
                    }
                )

            normalized_artifacts = []
            for item in ar + debug_artifacts:
                if isinstance(item, dict):
                    normalized_artifacts.append(item)
                else:
                    normalized_artifacts.append({"label": "artifact", "content": str(item)})

            return RagResult(ans, ev, normalized_artifacts)

        return RagResult(str(payload), [], [])
def call_rag_api(
    question: str,
    top_k: int,
    project_id: int | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
):

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
    if project_id is not None:
        payload["project_id"] = int(project_id)
    if llm_provider:
        payload["llm_provider"] = llm_provider
    if llm_model:
        payload["llm_model"] = llm_model

    r = requests.post(RAG_API_URL, json=payload, timeout=180)
    r.raise_for_status()

    try:
        data = r.json()
    except Exception:
        data = r.text

    return RagResult.from_any(data)
