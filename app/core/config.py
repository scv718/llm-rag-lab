import os
import re
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
from app.services.vector_store import VectorStore
from app.services.llm_provider import LLMSettings

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
REPO_DIR = DATA_DIR / "repos"
DOCS_DIR = DATA_DIR / "docs"
CHROMA_DIR = DATA_DIR / "chroma_db"

for d in (UPLOAD_DIR, REPO_DIR, DOCS_DIR, CHROMA_DIR):
    d.mkdir(parents=True, exist_ok=True)


def build_embedding_collection_name(model_name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", (model_name or "default").strip().lower()).strip("-")
    normalized = normalized[:48] if normalized else "default"
    return f"docs-{normalized}"


@dataclass(frozen=True)
class AppSettings:
    llm_provider: str
    llm_model: str
    local_llm_model: str
    retrieval_limit: int
    search_rerank_limit: int


SETTINGS = AppSettings(
    llm_provider=os.getenv("LLM_PROVIDER", "gemini"),
    llm_model=os.getenv("LLM_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash")),
    local_llm_model=os.getenv("LOCAL_LLM_MODEL", os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")),
    retrieval_limit=int(os.getenv("RETRIEVAL_LIMIT", "30")),
    search_rerank_limit=int(os.getenv("SEARCH_RERANK_LIMIT", "12")),
)

LLM_PROVIDER = SETTINGS.llm_provider
LLM_MODEL = SETTINGS.llm_model
LOCAL_LLM_MODEL = SETTINGS.local_llm_model
DEFAULT_RETRIEVAL_LIMIT = SETTINGS.retrieval_limit
SEARCH_RERANK_LIMIT = SETTINGS.search_rerank_limit

DEFAULT_LLM_SETTINGS = LLMSettings(
    provider=LLM_PROVIDER,
    model=LLM_MODEL,
    gemini_api_key=os.getenv("GEMINI_API_KEY"),
    openai_base_url=os.getenv("OPENAI_BASE_URL"),
    openai_api_key=os.getenv("OPENAI_API_KEY"),
)

vs = VectorStore(
    persist_directory=str(CHROMA_DIR),
    collection_name=build_embedding_collection_name(os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"))
)
