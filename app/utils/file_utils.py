from app.services.zip_ingest import TEXT_EXTS


DOCUMENT_EXTENSIONS = {
    ".pdf": "pdf",
    ".txt": "txt",
    ".md": "md",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".csv": "csv",
}

SINGLE_FILE_CODE_EXTENSIONS = {
    ".java",
    ".py",
    ".js",
    ".ts",
    ".xml",
    ".yml",
    ".yaml",
    ".sql",
}


def detect_file_kind(raw: bytes, filename: str) -> str:
    head = raw[:8]
    name = (filename or "").lower()

    if head.startswith(b"%PDF"):
        return "pdf"

    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06") or head.startswith(b"PK\x07\x08"):
        if name.endswith(".docx"):
            return "docx"
        if name.endswith(".xlsx"):
            return "xlsx"
        return "zip"

    for ext, kind in DOCUMENT_EXTENSIONS.items():
        if name.endswith(ext):
            return kind

    if name.endswith(".zip"):
        return "zip"

    if any(name.endswith(ext) for ext in SINGLE_FILE_CODE_EXTENSIONS):
        return "code"

    if any(name.endswith(ext) for ext in TEXT_EXTS):
        return "text"

    return "unknown"
