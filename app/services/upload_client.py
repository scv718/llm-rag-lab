import os
import requests


UPLOAD_API_URL = os.environ.get(
    "UPLOAD_API_URL",
    "http://127.0.0.1:8000/upload"
)


def upload_to_server(file_blob):

    files = {
        "file": (
            file_blob["name"],
            file_blob["bytes"],
            file_blob.get("mime") or "application/octet-stream",
        )
    }

    r = requests.post(
        UPLOAD_API_URL,
        files=files,
        timeout=300,
    )

    r.raise_for_status()

    return r.json()