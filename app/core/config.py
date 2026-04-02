import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from app.services.vector_store import VectorStore

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
REPO_DIR = DATA_DIR / "repos"
DOCS_DIR = DATA_DIR / "docs"
CHROMA_DIR = DATA_DIR / "chroma_db"

for d in (UPLOAD_DIR, REPO_DIR, DOCS_DIR, CHROMA_DIR):
    d.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class AppSettings:
    gemini_model: str
    retrieval_limit: int
    search_rerank_limit: int


SETTINGS = AppSettings(
    gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    retrieval_limit=int(os.getenv("RETRIEVAL_LIMIT", "30")),
    search_rerank_limit=int(os.getenv("SEARCH_RERANK_LIMIT", "12")),
)

GEMINI_MODEL = SETTINGS.gemini_model
DEFAULT_RETRIEVAL_LIMIT = SETTINGS.retrieval_limit
SEARCH_RERANK_LIMIT = SETTINGS.search_rerank_limit

gen_client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options=types.HttpOptions(api_version="v1"),
)

emb_client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options=types.HttpOptions(api_version="v1beta"),
)

vs = VectorStore(
    persist_directory=str(CHROMA_DIR),
    collection_name="docs"
)
