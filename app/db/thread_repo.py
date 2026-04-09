from .database import db_conn
from datetime import datetime


def now_ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def list_threads(project_id, q=""):

    conn = db_conn()

    if q.strip():
        rows = conn.execute(
            """
            SELECT * FROM threads
            WHERE project_id=?
            AND (title LIKE ? OR tag LIKE ?)
            ORDER BY updated_at DESC
            """,
            (project_id, f"%{q}%", f"%{q}%")
        ).fetchall()

    else:
        rows = conn.execute(
            "SELECT * FROM threads WHERE project_id=? ORDER BY updated_at DESC",
            (project_id,)
        ).fetchall()

    conn.close()
    return rows


def create_thread(project_id, title, tag="general"):

    conn = db_conn()
    cur = conn.cursor()

    ts = now_ts()

    cur.execute(
        """
        INSERT INTO threads(project_id,title,tag,created_at,updated_at)
        VALUES (?,?,?,?,?)
        """,
        (project_id,title,tag,ts,ts)
    )

    conn.commit()

    tid = cur.lastrowid
    conn.close()

    return tid


def delete_thread(thread_id):
    conn = db_conn()
    conn.execute("DELETE FROM turns WHERE thread_id=?", (thread_id,))
    conn.execute("DELETE FROM threads WHERE id=?", (thread_id,))
    conn.commit()
    conn.close()
