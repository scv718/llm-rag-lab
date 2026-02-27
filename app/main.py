# app/main.py
import os
import io
import traceback
import PyPDF2
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.services.chunking import chunk_text_by_chars, TextChunk
from app.services.vector_store import VectorStore
from app.services.embeddings import embed_documents, embed_query

load_dotenv()

app = FastAPI()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options=types.HttpOptions(api_version="v1"),
)

# ✅ 생성(답변)용: v1
gen_client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options=types.HttpOptions(api_version="v1"),
)

# ✅ 임베딩(검색)용: v1beta  ← 핵심
emb_client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options=types.HttpOptions(api_version="v1beta"),
)

# ✅ 로컬 영속 벡터DB(폴더에 저장)
vs = VectorStore(persist_directory="chroma_db", collection_name="docs")

knowledge_base = {
    "doc_id": "",
    "filename": "",
    "chunks": [],  # List[TextChunk]
}

class ChatRequest(BaseModel):
    message: str

class AskRequest(BaseModel):
    question: str
    top_k: int = 5


@app.post("/upload-doc")
async def upload_document(file: UploadFile = File(...)):
    try:
        content = await file.read()
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))

        doc_id = "doc-0001"  # MVP: 고정 (추후 sha256로 고유화 추천)
        filename = file.filename

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

        # ✅ 벡터DB 인덱싱: chunk → embedding → upsert
        chunk_texts = [c.text for c in all_chunks]
        if chunk_texts:
            vectors = embed_documents(emb_client, chunk_texts, title=filename)

            ids = [c.chunk_id for c in all_chunks]
            metadatas = [
                {
                    "doc_id": doc_id,
                    "filename": filename,
                    "page": c.page,
                    "chunk_index": c.chunk_index,
                    "chunk_id": c.chunk_id,   # ✅ 추가
                }
                for c in all_chunks
            ]
            vs.upsert(ids=ids, embeddings=vectors, metadatas=metadatas, documents=chunk_texts)

        knowledge_base["doc_id"] = doc_id
        knowledge_base["filename"] = filename
        knowledge_base["chunks"] = all_chunks

        return {
            "status": "success",
            "filename": filename,
            "doc_id": doc_id,
            "pages": len(pdf_reader.pages),
            "chunks": len(all_chunks),
            "indexed": len(all_chunks),
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/rag/ask")
def rag_ask(request: AskRequest):
    """
    질문 → 벡터 검색(top-k) → 검색된 chunk만 컨텍스트로 LLM 답변 생성
    """
    try:
        question = request.question.strip()
        top_k = max(1, min(int(request.top_k), 10))

        if not knowledge_base.get("doc_id"):
            raise HTTPException(status_code=400, detail="먼저 /upload-doc 로 문서를 업로드하세요.")

        qvec = embed_query(emb_client, question)

        # 문서 1개만 다루는 MVP라 doc_id로 필터
        hits = vs.query(query_embedding=qvec, n_results=top_k, where={"doc_id": knowledge_base["doc_id"]})

        # 컨텍스트 구성 + citations 생성
        context_lines = ["[참고 문서 발췌]"]
        citations = []
        for h in hits:
            md = h["metadata"]
            text = h["document"]
            dist = h["distance"]
            context_lines.append(f"- (page={md.get('page')}, chunk_id={md.get('chunk_id', '')}) {text}")
            citations.append(
                {
                    "filename": md.get("filename"),
                    "page": md.get("page"),
                    "chunk_id": md.get("chunk_id") or md.get("chunk_id", ""),  # 호환
                    "chunk_index": md.get("chunk_index"),
                    "distance": dist,
                }
            )

        context = "\n".join(context_lines)

        system = (
            "당신은 한국어로 답변하는 백엔드 전문가입니다. "
            "반드시 제공된 [참고 문서 발췌] 범위 안에서만 답하고, 근거가 부족하면 부족하다고 말하세요. "
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
        }

    except HTTPException:
        raise
    except Exception:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="RAG 처리 중 오류가 발생했습니다.")


@app.get("/chunks/preview")
def preview_chunks(limit: int = 5):
    chunks: list[TextChunk] = knowledge_base.get("chunks", [])
    preview = []
    for c in chunks[: max(0, limit)]:
        preview.append(
            {
                "chunk_id": c.chunk_id,
                "page": c.page,
                "chunk_index": c.chunk_index,
                "text": c.text[:200],
            }
        )
    return {
        "filename": knowledge_base.get("filename", ""),
        "doc_id": knowledge_base.get("doc_id", ""),
        "total_chunks": len(chunks),
        "preview": preview,
    }