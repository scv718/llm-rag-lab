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

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS project_targets (
            project_id INTEGER PRIMARY KEY,
            target_kind TEXT NOT NULL,
            target_ref_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )

    conn.commit()
    conn.close()