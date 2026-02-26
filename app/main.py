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

load_dotenv()

app = FastAPI()
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options=types.HttpOptions(api_version="v1"),
)

# ✅ 메모리 KB: MVP용 (추후 DB/VectorDB로 교체)
knowledge_base = {
    "doc_id": "",
    "filename": "",
    "content": "",   # 전체 텍스트(디버깅/확인용)
    "chunks": [],    # List[TextChunk]
}

class ChatRequest(BaseModel):
    message: str


@app.post("/upload-doc")
async def upload_document(file: UploadFile = File(...)):
    try:
        content = await file.read()
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))

        doc_id = "doc-0001"  # MVP: 고정. (추후 sha256 기반으로 문서ID 생성)
        all_text_parts = []
        all_chunks: list[TextChunk] = []

        for i, page in enumerate(pdf_reader.pages):
            page_no = i + 1
            page_text = page.extract_text() or ""
            all_text_parts.append(page_text)

            # ✅ 페이지 단위 chunk 생성 + page/chunk_id 메타 보존
            page_chunks = chunk_text_by_chars(
                doc_id=doc_id,
                page=page_no,
                text=page_text,
                chunk_size=900,
                overlap=150,
            )
            all_chunks.extend(page_chunks)

        extracted_text = "\n\n".join(all_text_parts).strip()

        knowledge_base["doc_id"] = doc_id
        knowledge_base["filename"] = file.filename
        knowledge_base["content"] = extracted_text
        knowledge_base["chunks"] = all_chunks

        return {
            "status": "success",
            "filename": file.filename,
            "doc_id": doc_id,
            "pages": len(pdf_reader.pages),
            "chunks": len(all_chunks),
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat")
def chat(request: ChatRequest):
    try:
        # ✅ 아직 RAG는 안 붙였으니, 임시로 "상위 N개 chunk"만 컨텍스트로 넣는다.
        # 다음 커밋에서 "질문 → 검색(top-k)"로 바뀐다.
        chunks: list[TextChunk] = knowledge_base.get("chunks", [])
        context_chunks = chunks[:6]  # MVP 임시
        context = ""
        if context_chunks:
            context_lines = []
            context_lines.append("[참고 문서 발췌]")
            for c in context_chunks:
                context_lines.append(f"- (page={c.page}, chunk_id={c.chunk_id}) {c.text}")
            context = "\n".join(context_lines)

        system = "당신은 한국어로 답변하는 백엔드 전문가입니다. 마지막에 질문으로 끝내지 마세요."
        prompt = f"[SYSTEM]\n{system}\n\n[USER]\n{request.message}\n\n{context}"

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return {"response": response.text}

    except Exception:
        print("\n=== 에러 발생 상세 로그 ===")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Gemini API 호출 중 오류가 발생했습니다.")