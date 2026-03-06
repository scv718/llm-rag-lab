from pathlib import Path
import hashlib
from .database import db_conn
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"


def now_ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _proj_doc_dir(project_id):
    p = DATA_DIR / "projects" / str(project_id) / "docs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def list_project_docs(project_id):
    conn = db_conn()
    rows = conn.execute(
        "SELECT * FROM project_docs WHERE project_id=? ORDER BY created_at DESC",
        (project_id,)
    ).fetchall()
    conn.close()
    return rows


def save_project_doc(project_id, f, doc_id):
    raw = f.getvalue()
    sha = hashlib.sha256(raw).hexdigest()

    conn = db_conn()

    row = conn.execute(
        "SELECT id FROM project_docs WHERE project_id=? AND sha256=?",
        (project_id, sha)
    ).fetchone()

    if row:
        conn.close()
        return int(row["id"])

    dirp = _proj_doc_dir(project_id)
    out_path = dirp / f.name
    out_path.write_bytes(raw)

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO project_docs
        (project_id, filename, mime, size, sha256, doc_id, stored_path, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project_id,
            f.name,
            getattr(f, "type", None),
            len(raw),
            sha,
            doc_id,
            str(out_path),
            now_ts(),
        ),
    )

    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def delete_project_doc(doc_id):
    conn = db_conn()

    row = conn.execute(
        "SELECT stored_path FROM project_docs WHERE id=?",
        (doc_id,)
    ).fetchone()

    if row and row["stored_path"]:
        Path(row["stored_path"]).unlink(missing_ok=True)

    conn.execute("DELETE FROM project_docs WHERE id=?", (doc_id,))
    conn.commit()
    conn.close()