from datetime import datetime
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