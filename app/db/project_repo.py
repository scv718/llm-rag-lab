from datetime import datetime
from pathlib import Path
import shutil

from .database import db_conn


def now_ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def list_projects():
    conn = db_conn()
    rows = conn.execute(
        "SELECT * FROM projects ORDER BY created_at DESC, id DESC"
    ).fetchall()
    conn.close()
    return rows


def create_project(name):
    conn = db_conn()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO projects(name, created_at) VALUES (?, ?)",
        (name, now_ts())
    )

    conn.commit()
    pid = cur.lastrowid
    conn.close()

    return pid


def delete_project(project_id):
    conn = db_conn()

    doc_rows = conn.execute(
        "SELECT stored_path FROM project_docs WHERE project_id=?",
        (project_id,),
    ).fetchall()
    for row in doc_rows:
        if row["stored_path"]:
            Path(row["stored_path"]).unlink(missing_ok=True)

    repo_rows = conn.execute(
        "SELECT zip_path, extract_path FROM project_repos WHERE project_id=?",
        (project_id,),
    ).fetchall()
    for row in repo_rows:
        if row["zip_path"]:
            Path(row["zip_path"]).unlink(missing_ok=True)
        if row["extract_path"]:
            shutil.rmtree(row["extract_path"], ignore_errors=True)

    thread_rows = conn.execute(
        "SELECT id FROM threads WHERE project_id=?",
        (project_id,),
    ).fetchall()
    for row in thread_rows:
        conn.execute("DELETE FROM turns WHERE thread_id=?", (row["id"],))

    conn.execute("DELETE FROM threads WHERE project_id=?", (project_id,))
    conn.execute("DELETE FROM project_docs WHERE project_id=?", (project_id,))
    conn.execute("DELETE FROM project_repos WHERE project_id=?", (project_id,))
    conn.execute("DELETE FROM project_targets WHERE project_id=?", (project_id,))
    conn.execute("DELETE FROM project_target_settings WHERE project_id=?", (project_id,))
    conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
    conn.commit()
    conn.close()

    project_dir = Path(__file__).resolve().parent.parent.parent / "data" / "projects" / str(project_id)
    shutil.rmtree(project_dir, ignore_errors=True)
