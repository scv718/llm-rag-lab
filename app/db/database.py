import sqlite3
import os


DB_PATH = os.environ.get("LLM_UI_DB", "llm_ui.db")


def db_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def db_init():
    conn = db_conn()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS threads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            tag TEXT NOT NULL DEFAULT 'general',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            payload_json TEXT,
            created_at TEXT NOT NULL
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS project_docs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            mime TEXT,
            size INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(project_id, sha256)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS project_repos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            repo_id TEXT NOT NULL,
            zip_path TEXT NOT NULL,
            extract_path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(project_id, sha256)
        );
        """
    )

    _ensure_project_targets_schema(cur)

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS project_target_settings (
            project_id INTEGER PRIMARY KEY,
            active_only INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );
        """
    )

    conn.commit()
    conn.close()


def _ensure_project_targets_schema(cur):
    table = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='project_targets'"
    ).fetchone()

    if not table:
        cur.execute(
            """
            CREATE TABLE project_targets (
                project_id INTEGER NOT NULL,
                target_kind TEXT NOT NULL,
                target_ref_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(project_id, target_kind, target_ref_id)
            );
            """
        )
        return

    columns = cur.execute("PRAGMA table_info(project_targets)").fetchall()
    column_names = [row[1] for row in columns]
    project_id_column = next((row for row in columns if row[1] == "project_id"), None)
    uses_legacy_single_target = bool(project_id_column and project_id_column[5] == 1 and "target_ref_id" in column_names)

    if not uses_legacy_single_target:
        return

    cur.execute("ALTER TABLE project_targets RENAME TO project_targets_legacy")
    cur.execute(
        """
        CREATE TABLE project_targets (
            project_id INTEGER NOT NULL,
            target_kind TEXT NOT NULL,
            target_ref_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(project_id, target_kind, target_ref_id)
        );
        """
    )
    cur.execute(
        """
        INSERT INTO project_targets (project_id, target_kind, target_ref_id, filename, updated_at)
        SELECT project_id, target_kind, target_ref_id, filename, updated_at
        FROM project_targets_legacy
        """
    )
    cur.execute("DROP TABLE project_targets_legacy")
