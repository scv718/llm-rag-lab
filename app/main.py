import os
import io
import traceback
import PyPDF2
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

app = FastAPI()

# ✅ v1로 고정 (v1beta 기본값 회피)
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options=types.HttpOptions(api_version="v1"),
)

knowledge_base = {"content": ""}

class ChatRequest(BaseModel):
    message: str

@app.post("/upload-doc")
async def upload_document(file: UploadFile = File(...)):
    try:
        content = await file.read()
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
        extracted_text = ""
        for page in pdf_reader.pages:
            extracted_text += (page.extract_text() or "")
        knowledge_base["content"] = extracted_text
        return {"status": "success", "filename": file.filename}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
def chat(request: ChatRequest):
    try:
        context = f"\n\n[참고 문서]\n{knowledge_base['content']}" if knowledge_base["content"] else ""

        system = "당신은 한국어로 답변하는 백엔드 전문가입니다."
        prompt = f"[SYSTEM]\n{system}\n\n[USER]\n{request.message}{context}"

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            # ✅ config에서 system_instruction 제거
            config=types.GenerateContentConfig(),
        )
        return {"response": response.text}

    except Exception:
        print("\n=== 에러 발생 상세 로그 ===")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Gemini API 호출 중 오류가 발생했습니다.")