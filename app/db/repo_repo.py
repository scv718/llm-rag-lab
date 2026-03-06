from datetime import datetime
from .database import db_conn


def now_ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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


def list_project_repos(project_id):
    conn = db_conn()
    rows = conn.execute(
        "SELECT * FROM project_repos WHERE project_id=? ORDER BY created_at DESC",
        (project_id,)
    ).fetchall()
    conn.close()
    return rows