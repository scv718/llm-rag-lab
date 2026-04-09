from fastapi import FastAPI, UploadFile, File, Form
from pydantic import BaseModel

from app.services.file_services import ingest_upload
from app.services.rag_service import ask_rag

app = FastAPI()


class AskRequest(BaseModel):
    question: str
    top_k: int = 10
    project_id: int | None = None
    llm_provider: str | None = None
    llm_model: str | None = None


@app.post("/upload")
async def upload(
    file: UploadFile = File(...),
    project_id: int | None = Form(default=None),
):
    raw = await file.read()
    filename = file.filename or "uploaded"
    return ingest_upload(raw, filename, project_id=project_id)


@app.post("/rag/ask")
def rag_ask(request: AskRequest):
    return ask_rag(
        request.question,
        request.top_k,
        project_id=request.project_id,
        llm_provider=request.llm_provider,
        llm_model=request.llm_model,
    )
