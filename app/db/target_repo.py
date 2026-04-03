from datetime import datetime
from .database import db_conn


def now_ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def add_project_target(project_id, target_kind, target_ref_id, filename):
    conn = db_conn()
    conn.execute(
        """
        INSERT INTO project_targets
        (project_id, target_kind, target_ref_id, filename, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(project_id, target_kind, target_ref_id) DO UPDATE SET
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


def remove_project_target(project_id, target_kind, target_ref_id):
    conn = db_conn()
    conn.execute(
        """
        DELETE FROM project_targets
        WHERE project_id=? AND target_kind=? AND target_ref_id=?
        """,
        (project_id, target_kind, target_ref_id),
    )
    conn.commit()
    conn.close()


def list_project_targets(project_id):
    conn = db_conn()
    rows = conn.execute(
        """
        SELECT * FROM project_targets
        WHERE project_id=?
        ORDER BY target_kind, filename, updated_at DESC
        """,
        (project_id,),
    ).fetchall()
    conn.close()
    return rows


def get_project_target_settings(project_id):
    conn = db_conn()
    row = conn.execute(
        """
        SELECT * FROM project_target_settings
        WHERE project_id=?
        """,
        (project_id,),
    ).fetchone()
    conn.close()
    return row


def set_project_targeting_mode(project_id, active_only):
    conn = db_conn()
    conn.execute(
        """
        INSERT INTO project_target_settings
        (project_id, active_only, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(project_id) DO UPDATE SET
            active_only=excluded.active_only,
            updated_at=excluded.updated_at
        """,
        (project_id, 1 if active_only else 0, now_ts()),
    )
    conn.commit()
    conn.close()


def clear_project_targets(project_id):
    conn = db_conn()
    conn.execute("DELETE FROM project_targets WHERE project_id=?", (project_id,))
    conn.commit()
    conn.close()
