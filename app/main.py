# app/main.py (필요 부분만 발췌/교체)

import os
import io
import traceback
import hashlib
import PyPDF2

from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pathlib import Path

from app.services.chunking import chunk_text_by_chars, TextChunk
from app.services.vector_store import VectorStore
from app.services.embeddings import embed_documents, embed_query

from app.services.zip_ingest import (
    safe_extract_zip,
    iter_source_files,
    read_text_best_effort,
    chunk_code_by_lines,
    CodeChunk,
)

load_dotenv()
app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
REPO_DIR = DATA_DIR / "repos"
DOCS_DIR = DATA_DIR / "docs"
CHROMA_DIR = DATA_DIR / "chroma_db"

for d in (UPLOAD_DIR, REPO_DIR, DOCS_DIR, CHROMA_DIR):
    d.mkdir(parents=True, exist_ok=True)

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def detect_file_kind(raw: bytes, filename: str) -> str:
    head = raw[:8]
    name = (filename or "").lower()

    if head.startswith(b"%PDF"):
        return "pdf"

    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06") or head.startswith(b"PK\x07\x08"):
        return "zip"

    if name.endswith(".pdf"):
        return "pdf"
    if name.endswith(".zip"):
        return "zip"

    return "unknown"

# Gemini clients
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options=types.HttpOptions(api_version="v1"),
)

gen_client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options=types.HttpOptions(api_version="v1"),
)

emb_client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options=types.HttpOptions(api_version="v1beta"),
)

# VectorStore
vs = VectorStore(persist_directory=str(CHROMA_DIR), collection_name="docs")

# (선택) 최근 업로드 대상만 추적(MVP용). 여러 repo/doc 동시 지원하려면 제거/확장.
latest_target = {
    "kind": "",     # "doc" | "code"
    "id": "",       # doc_id | repo_id
    "filename": "",
}

class AskRequest(BaseModel):
    question: str
    top_k: int = 200

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    """
    단일 업로드 엔드포인트:
    - PDF면 문서 ingest
    - ZIP면 소스 ingest
    서버가 자동 판별
    """
    try:
        print("CHROMA PATH:", CHROMA_DIR)
        raw = await file.read()
        filename = file.filename or "uploaded"

        kind = detect_file_kind(raw, filename)
        if kind == "unknown":
            raise HTTPException(status_code=400, detail="지원하지 않는 파일 형식입니다. (PDF/ZIP만 지원)")

        # -------------------------
        # PDF ingest
        # -------------------------
        if kind == "pdf":
            # doc_id: 콘텐츠 기반
            doc_id = f"doc-{sha256_bytes(raw)[:16]}"
            pdf_path = DOCS_DIR / f"{doc_id}.pdf"
            pdf_path.write_bytes(raw)

            pdf_reader = PyPDF2.PdfReader(io.BytesIO(raw))
            all_chunks: list[TextChunk] = []

            for i, page in enumerate(pdf_reader.pages):
                page_no = i + 1
                page_text = page.extract_text() or ""

                page_chunks = chunk_text_by_chars(
                    doc_id=doc_id,
                    page=page_no,
                    text=page_text,
                    chunk_size=900,
                    overlap=150,
                )
                all_chunks.extend(page_chunks)

            chunk_texts = [c.text for c in all_chunks]
            if chunk_texts:
                vectors = embed_documents(chunk_texts)

                ids = [c.chunk_id for c in all_chunks]
                metadatas = [
                    {
                        "kind": "doc",
                        "doc_id": doc_id,
                        "filename": filename,
                        "page": c.page,
                        "chunk_index": c.chunk_index,
                        "chunk_id": c.chunk_id,
                    }
                    for c in all_chunks
                ]
                vs.upsert(ids=ids, embeddings=vectors, metadatas=metadatas, documents=chunk_texts)

            latest_target["kind"] = "doc"
            latest_target["id"] = doc_id
            latest_target["filename"] = filename

            return {
                "status": "success",
                "kind": "doc",
                "doc_id": doc_id,
                "filename": filename,
                "pages": len(pdf_reader.pages),
                "chunks": len(all_chunks),
                "indexed": len(all_chunks),
            }

        # -------------------------
        # ZIP (code) ingest
        # -------------------------
        if kind == "zip":
            repo_id = sha256_bytes(raw)[:16]
            zip_path = UPLOAD_DIR / f"{repo_id}.zip"
            zip_path.write_bytes(raw)

            extract_dir = REPO_DIR / repo_id

            # 기존 폴더가 있으면 덮어쓰기 충돌 위험이 있으니 정리 후 재해제하는 게 안전
            # MVP 최소 구현: 이미 있으면 그대로 재활용 가능하지만, 충돌 방지 차원에서 삭제 권장
            if extract_dir.exists():
                # 표준 라이브러리로 재귀삭제(가벼운 구현)
                import shutil
                shutil.rmtree(extract_dir, ignore_errors=True)

            extracted_files, total_bytes = safe_extract_zip(
                zip_path=zip_path,
                extract_dir=extract_dir,
                max_files=8000,
                max_total_uncompressed_bytes=300 * 1024 * 1024,
            )

            all_chunks: list[CodeChunk] = []
            for src in iter_source_files(extract_dir):
                rel_path = str(src.relative_to(extract_dir)).replace("\\", "/")
                text = read_text_best_effort(src)
                all_chunks.extend(
                    chunk_code_by_lines(
                        repo_id=repo_id,
                        rel_path=rel_path,
                        text=text,
                        lines_per_chunk=250,
                        overlap=40,
                    )
                )

            texts = [c.text for c in all_chunks]
            if texts:
                vectors = embed_documents(texts)

                ids = [c.chunk_id for c in all_chunks]
                metadatas = [
                    {
                        "kind": "code",
                        "repo_id": repo_id,
                        "filename": filename,
                        "path": c.path,
                        "lang": c.lang,
                        "start_line": c.start_line,
                        "end_line": c.end_line,
                        "chunk_id": c.chunk_id,
                    }
                    for c in all_chunks
                ]
                vs.upsert(ids=ids, embeddings=vectors, metadatas=metadatas, documents=texts)

            latest_target["kind"] = "code"
            latest_target["id"] = repo_id
            latest_target["filename"] = filename

            return {
                "status": "success",
                "kind": "code",
                "repo_id": repo_id,
                "filename": filename,
                "extracted_files": extracted_files,
                "uncompressed_bytes": total_bytes,
                "chunks": len(all_chunks),
                "indexed": len(all_chunks),
            }

        raise HTTPException(status_code=400, detail="알 수 없는 업로드 유형입니다.")

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/rag/ask")
def rag_ask(request: AskRequest):
    """
    질문 → 벡터 검색(top-k) → 검색된 chunk만 컨텍스트로 LLM 답변 생성
    - 최신 업로드 대상(latest_target)에 대해서만 검색(MVP)
    - doc/code 둘 다 들어오면 kind 필터로 제어
    """
    try:
        question = request.question.strip()
        top_k = max(1, min(int(request.top_k), 10))

        if not latest_target.get("id"):
            raise HTTPException(status_code=400, detail="먼저 /upload 로 PDF 또는 ZIP을 업로드하세요.")

        qvec = embed_query(question)

        where = None
        if latest_target["kind"] == "doc":
            where = {"$and": [{"kind": "doc"}, {"doc_id": latest_target["id"]}]}
        elif latest_target["kind"] == "code":
            where = {"$and": [{"kind": "code"}, {"repo_id": latest_target["id"]}]}

        hits = vs.query(query_embedding=qvec, n_results=top_k, where=where)
        context_lines = ["[참고 발췌]"]
        citations = []

        for h in hits:
            md = h["metadata"]
            text = h["document"]
            dist = h["distance"]

            if md.get("kind") == "doc":
                context_lines.append(f"- (kind=doc, page={md.get('page')}, chunk_id={md.get('chunk_id','')}) {text}")
                citations.append({
                    "kind": "doc",
                    "filename": md.get("filename"),
                    "page": md.get("page"),
                    "chunk_id": md.get("chunk_id"),
                    "chunk_index": md.get("chunk_index"),
                    "distance": dist,
                })
            else:
                context_lines.append(
                    f"- (kind=code, path={md.get('path')}, L{md.get('start_line')}-L{md.get('end_line')}, chunk_id={md.get('chunk_id','')}) {text}"
                )
                citations.append({
                    "kind": "code",
                    "filename": md.get("filename"),
                    "path": md.get("path"),
                    "start_line": md.get("start_line"),
                    "end_line": md.get("end_line"),
                    "chunk_id": md.get("chunk_id"),
                    "distance": dist,
                })

        context = "\n".join(context_lines)

        system = (
            "당신은 한국어로 답변하는 백엔드 전문가입니다. "
            "반드시 제공된 [참고 발췌] 범위 안에서만 답하고, 근거가 부족하면 부족하다고 말하세요. "
            "마지막에 질문으로 끝내지 마세요."
        )
        prompt = f"[SYSTEM]\n{system}\n\n[USER]\n{question}\n\n{context}"

        resp = gen_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )

        return {
            "answer": resp.text,
            "citations": citations,
            "retrieved_k": len(hits),
            "target": latest_target,
        }

    except HTTPException:
        raise
    except Exception:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="RAG 처리 중 오류가 발생했습니다.")