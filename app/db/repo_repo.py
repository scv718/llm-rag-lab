from datetime import datetime
import hashlib
from pathlib import Path
from .database import db_conn

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"


def now_ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _proj_repo_dir(project_id):
    path = DATA_DIR / "projects" / str(project_id) / "repos"
    path.mkdir(parents=True, exist_ok=True)
    return path


def insert_project_repo(project_id, filename, sha256, repo_id, zip_path, extract_path):
    conn = db_conn()

    row = conn.execute(
        "SELECT id FROM project_repos WHERE project_id=? AND sha256=?",
        (project_id, sha256)
    ).fetchone()

    if row:
        conn.close()
        return int(row["id"])

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO project_repos
        (project_id, filename, sha256, repo_id, zip_path, extract_path, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project_id,
            filename,
            sha256,
            repo_id,
            zip_path,
            extract_path,
            now_ts(),
        ),
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def save_project_repo_blob(project_id, filename, raw, repo_id, extract_path):
    sha256 = hashlib.sha256(raw).hexdigest()
    repo_dir = _proj_repo_dir(project_id)
    zip_path = repo_dir / f"{repo_id}_{filename}"
    zip_path.write_bytes(raw)
    return insert_project_repo(
        project_id=project_id,
        filename=filename,
        sha256=sha256,
        repo_id=repo_id,
        zip_path=str(zip_path),
        extract_path=extract_path,
    )


def list_project_repos(project_id):
    conn = db_conn()
    rows = conn.execute(
        "SELECT * FROM project_repos WHERE project_id=? ORDER BY created_at DESC",
        (project_id,)
    ).fetchall()
    conn.close()
    return rows


def delete_project_repo(repo_row_id):
    conn = db_conn()

    row = conn.execute(
        "SELECT zip_path FROM project_repos WHERE id=?",
        (repo_row_id,)
    ).fetchone()

    if row and row["zip_path"]:
        Path(row["zip_path"]).unlink(missing_ok=True)

    conn.execute("DELETE FROM project_repos WHERE id=?", (repo_row_id,))
    conn.commit()
    conn.close()
