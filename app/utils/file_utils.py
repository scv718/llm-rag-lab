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