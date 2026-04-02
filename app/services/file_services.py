import io
import traceback

import PyPDF2
from fastapi import HTTPException

from app.core.config import DOCS_DIR, REPO_DIR, UPLOAD_DIR, vs
from app.core.state import latest_target
from app.db.target_repo import upsert_project_target
from app.services.chunking import TextChunk, chunk_text_by_chars
from app.services.embeddings import embed_documents
from app.services.zip_ingest import (
    CodeChunk,
    chunk_code_by_lines,
    iter_source_files,
    read_text_best_effort,
    safe_extract_zip,
)
from app.utils.file_utils import detect_file_kind
from app.utils.hash_utils import sha256_bytes


def ingest_upload(raw: bytes, filename: str, project_id: int | None = None) -> dict:
    kind = detect_file_kind(raw, filename)
    if kind == "unknown":
        raise HTTPException(status_code=400, detail="지원하지 않는 파일 형식입니다. (PDF/ZIP만 지원)")

    try:
        if kind == "pdf":
            return ingest_pdf(raw, filename, project_id=project_id)
        if kind == "zip":
            return ingest_zip(raw, filename, project_id=project_id)
    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    raise HTTPException(status_code=400, detail="알 수 없는 업로드 유형입니다.")


def ingest_pdf(raw: bytes, filename: str, project_id: int | None = None) -> dict:
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

    if project_id is not None:
        upsert_project_target(project_id, "doc", doc_id, filename)

    return {
        "status": "success",
        "kind": "doc",
        "doc_id": doc_id,
        "filename": filename,
        "project_id": project_id,
        "pages": len(pdf_reader.pages),
        "chunks": len(all_chunks),
        "indexed": len(all_chunks),
        "stored_path": str(pdf_path),
    }


def ingest_zip(raw: bytes, filename: str, project_id: int | None = None) -> dict:
    repo_id = sha256_bytes(raw)[:16]
    zip_path = UPLOAD_DIR / f"{repo_id}.zip"
    zip_path.write_bytes(raw)

    extract_dir = REPO_DIR / repo_id
    if extract_dir.exists():
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

    if project_id is not None:
        upsert_project_target(project_id, "code", repo_id, filename)

    return {
        "status": "success",
        "kind": "code",
        "repo_id": repo_id,
        "filename": filename,
        "project_id": project_id,
        "extracted_files": extracted_files,
        "uncompressed_bytes": total_bytes,
        "chunks": len(all_chunks),
        "indexed": len(all_chunks),
        "zip_path": str(zip_path),
        "extract_path": str(extract_dir),
    }
