from datetime import datetime
from .database import db_conn


def now_ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def upsert_project_target(project_id, target_kind, target_ref_id, filename):
    conn = db_conn()
    conn.execute(
        """
        INSERT INTO project_targets
        (project_id, target_kind, target_ref_id, filename, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(project_id) DO UPDATE SET
            target_kind=excluded.target_kind,
            target_ref_id=excluded.target_ref_id,
            filename=excluded.filename,
            updated_at=excluded.updated_at
        """,
        (
            project_id,
            target_kind,
            target_ref_id,
            filename,
            now_ts(),
        ),
    )
    conn.commit()
    conn.close()


def get_project_target(project_id):
    conn = db_conn()
    row = conn.execute(
        "SELECT * FROM project_targets WHERE project_id=?",
        (project_id,)
    ).fetchone()
    conn.close()
    return row