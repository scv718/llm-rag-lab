from .database import db_conn
import json
from datetime import datetime


def now_ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def list_turns(thread_id):

    conn = db_conn()

    rows = conn.execute(
        "SELECT * FROM turns WHERE thread_id=? ORDER BY id ASC",
        (thread_id,)
    ).fetchall()

    conn.close()

    return rows


def add_turn(thread_id, role, content, payload=None):

    conn = db_conn()

    cur = conn.cursor()

    payload_json = json.dumps(payload, ensure_ascii=False) if payload else None

    cur.execute(
        """
        INSERT INTO turns(thread_id, role, content, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            thread_id,
            role,
            content,
            payload_json,
            now_ts()
        )
    )

    cur.execute(
        """
        UPDATE threads
        SET updated_at=?
        WHERE id=?
        """,
        (now_ts(), thread_id)
    )

    conn.commit()

    rid = cur.lastrowid

    conn.close()

    return rid

def delete_turns(thread_id: int, turn_ids: list[int]):
    if not turn_ids:
        return

    conn = db_conn()
    cur = conn.cursor()

    placeholders = ",".join(["?"] * len(turn_ids))
    params = [thread_id, *turn_ids]

    cur.execute(
        f"""
        DELETE FROM turns
        WHERE thread_id = ?
          AND id IN ({placeholders})
        """,
        params
    )

    conn.commit()
    conn.close()
