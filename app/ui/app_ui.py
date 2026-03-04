# ui/app_ui.py
# PPT형 3패널 UI: 작업목록 | (질문리스트/채팅) | 답변
# 실행:
#   python -m streamlit run ui/app_ui.py --server.port 8501

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from pathlib import Path
import hashlib

import requests
import streamlit as st


# =========================
# Config
# =========================
APP_TITLE = "RAG Q/A Tool"
DB_PATH = os.environ.get("LLM_UI_DB", "llm_ui.db")
DATA_DIR = os.environ.get("LLM_UI_DATA", "app/data")

RAG_API_URL = os.environ.get("RAG_API_URL", "http://127.0.0.1:8000/rag/ask")
UPLOAD_API_URL = os.environ.get("UPLOAD_API_URL", "http://127.0.0.1:8000/upload")
DEFAULT_TOP_K = int(os.environ.get("RAG_TOP_K", "5"))
USE_REAL_API = os.environ.get("USE_REAL_API", "false").lower() == "true"


# =========================
# DB
# =========================
def db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def db_init() -> None:
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
            updated_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id INTEGER NOT NULL,
            role TEXT NOT NULL,  -- user|assistant
            content TEXT NOT NULL,
            payload_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(thread_id) REFERENCES threads(id)
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
            sha256 TEXT,
            stored_path TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        );
        """
    )
    
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS uploads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        kind TEXT NOT NULL,     -- doc|code
        target_id TEXT NOT NULL, -- doc_id|repo_id
        filename TEXT NOT NULL,
        created_at TEXT NOT NULL
        );
        """
    )
    
    conn.commit()
    conn.close()


def list_projects() -> list[sqlite3.Row]:
    conn = db_conn()
    # 최신 생성 프로젝트가 위로
    rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC, id DESC").fetchall()
    conn.close()
    return rows


def create_project(name: str) -> int:
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO projects(name, created_at) VALUES (?, ?)", (name, now_ts()))
    conn.commit()
    pid = int(cur.lastrowid)
    conn.close()
    return pid


def list_threads(project_id: int, q: str = "") -> list[sqlite3.Row]:
    conn = db_conn()
    if q.strip():
        rows = conn.execute(
            """
            SELECT * FROM threads
            WHERE project_id = ?
              AND (title LIKE ? OR tag LIKE ?)
            ORDER BY updated_at DESC, id DESC
            """,
            (project_id, f"%{q.strip()}%", f"%{q.strip()}%"),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM threads
            WHERE project_id = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (project_id,),
        ).fetchall()
    conn.close()
    return rows


def create_thread(project_id: int, title: str, tag: str = "general") -> int:
    conn = db_conn()
    cur = conn.cursor()
    ts = now_ts()
    cur.execute(
        """
        INSERT INTO threads(project_id, title, tag, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (project_id, title, tag, ts, ts),
    )
    conn.commit()
    tid = int(cur.lastrowid)
    conn.close()
    return tid


def touch_thread(thread_id: int) -> None:
    conn = db_conn()
    conn.execute("UPDATE threads SET updated_at = ? WHERE id = ?", (now_ts(), thread_id))
    conn.commit()
    conn.close()


def list_turns(thread_id: int) -> list[sqlite3.Row]:
    conn = db_conn()
    rows = conn.execute("SELECT * FROM turns WHERE thread_id = ? ORDER BY id ASC", (thread_id,)).fetchall()
    conn.close()
    return rows


def add_turn(thread_id: int, role: str, content: str, payload: Optional[dict[str, Any]] = None) -> int:
    conn = db_conn()
    cur = conn.cursor()
    payload_json = json.dumps(payload, ensure_ascii=False) if payload else None
    cur.execute(
        """
        INSERT INTO turns(thread_id, role, content, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (thread_id, role, content, payload_json, now_ts()),
    )
    conn.commit()
    rid = int(cur.lastrowid)
    conn.close()
    touch_thread(thread_id)
    return rid

def _proj_doc_dir(project_id: int) -> Path:
    p = Path(DATA_DIR) / "projects" / str(project_id) / "docs"
    p.mkdir(parents=True, exist_ok=True)
    return p

def list_project_docs(project_id: int) -> list[sqlite3.Row]:
    conn = db_conn()
    rows = conn.execute(
        "SELECT * FROM project_docs WHERE project_id=? ORDER BY created_at DESC, id DESC",
        (project_id,),
    ).fetchall()
    conn.close()
    return rows

def upload_to_server(file_blob: dict[str, Any]) -> dict[str, Any]:
    files = {
        "file": (file_blob["name"], file_blob["bytes"], file_blob.get("mime") or "application/octet-stream")
    }
    r = requests.post(UPLOAD_API_URL, files=files, timeout=300)
    r.raise_for_status()
    return r.json()

def save_project_doc(project_id: int, f) -> int:
    raw = f.getvalue()
    sha = hashlib.sha256(raw).hexdigest()

    dirp = _proj_doc_dir(project_id)
    out_path = dirp / f.name
    if out_path.exists():
        stem, dot, ext = f.name.partition(".")
        out_path = dirp / (f"{stem}.{sha[:8]}.{ext}" if dot else f"{stem}.{sha[:8]}")

    out_path.write_bytes(raw)

    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO project_docs(project_id, filename, mime, size, sha256, stored_path, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (project_id, f.name, getattr(f, "type", None), len(raw), sha, str(out_path), now_ts()),
    )
    conn.commit()
    rid = int(cur.lastrowid)
    conn.close()
    return rid

def delete_project_doc(doc_id: int) -> None:
    conn = db_conn()
    row = conn.execute("SELECT stored_path FROM project_docs WHERE id=?", (doc_id,)).fetchone()
    if row and row["stored_path"]:
        try:
            Path(row["stored_path"]).unlink(missing_ok=True)
        except Exception:
            pass
    conn.execute("DELETE FROM project_docs WHERE id=?", (doc_id,))
    conn.commit()
    conn.close()
# =========================
# RAG API
# =========================
@dataclass
class RagResult:
    answer_markdown: str
    evidence: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]

    @staticmethod
    def from_any(payload: Any) -> "RagResult":
        if isinstance(payload, str):
            return RagResult(payload, [], [])
        if isinstance(payload, dict):
            ans = payload.get("answer_markdown") or payload.get("answer") or payload.get("text") or ""
            ev = payload.get("evidence") or payload.get("citations") or []
            ar = payload.get("artifacts") or []
            if not isinstance(ev, list):
                ev = []
            if not isinstance(ar, list):
                ar = []
            return RagResult(str(ans), ev, ar)
        return RagResult(str(payload), [], [])


def call_rag_api(question: str, top_k: int, extra_context: Optional[dict[str, Any]] = None) -> RagResult:
    if not USE_REAL_API:
        demo = {
            "answer_markdown": f"### (DEMO)\n질문: `{question}`\n\n- 여기서 실제 LLM 답변을 표시\n- 우측 패널에 Answer/Evidence/Artifacts로 분리 표시",
            "evidence": [
                {"title": "예시 근거", "path": "/docs/exception.md", "lines": "L10-L30", "snippet": "예외 처리 정책 ..."}
            ],
            "artifacts": [
                {"type": "code", "title": "예시 코드", "content": "def foo():\n    return 1\n"}
            ],
        }
        return RagResult.from_any(demo)

    payload = {"question": question, "top_k": int(top_k)}
    r = requests.post(RAG_API_URL, json=payload, timeout=180)
    r.raise_for_status()
    try:
        data = r.json()
    except Exception:
        data = r.text
    return RagResult.from_any(data)


# =========================
# Session State
# =========================
def ensure_state() -> None:
    st.session_state.setdefault("selected_project_id", None)
    st.session_state.setdefault("selected_thread_id", None)
    st.session_state.setdefault("thread_search", "")
    st.session_state.setdefault("top_k", DEFAULT_TOP_K)

    st.session_state.setdefault("new_project_name", "")
    st.session_state.setdefault("new_thread_title", "")

    st.session_state.setdefault("clear_new_project_name", False)
    st.session_state.setdefault("clear_new_thread_title", False)

    st.session_state.setdefault("upload_blobs", [])
    st.session_state.setdefault("chat_input", "")


def set_project(pid: int) -> None:
    st.session_state["selected_project_id"] = pid
    st.session_state["selected_thread_id"] = None


def set_thread(tid: int) -> None:
    st.session_state["selected_thread_id"] = tid


def payload_from_row(row: sqlite3.Row) -> Optional[dict[str, Any]]:
    pj = row["payload_json"]
    if not pj:
        return None
    try:
        return json.loads(pj)
    except Exception:
        return None


def last_assistant_payload(turns: list[sqlite3.Row]) -> Optional[dict[str, Any]]:
    for r in reversed(turns):
        if r["role"] == "assistant":
            p = payload_from_row(r)
            if p:
                return p
    return None


# =========================
# CSS: PPT형 고정 레이아웃 + 내부 스크롤
# =========================
def inject_css() -> None:
    st.markdown(
        """
<style>
/* 전체 폭/여백 */
.block-container { padding-top: 1.2rem; padding-bottom: 1.2rem; }

/* 패널 느낌 */
.panel {
  border: 1px solid rgba(49,51,63,0.15);
  border-radius: 10px;
  padding: 12px 12px 10px 12px;
  background: #fff;
}

/* 패널 제목 */
.panel-title {
  font-weight: 800;
  font-size: 1.05rem;
  margin-bottom: 8px;
}

/* 내부 스크롤 영역 */
.scroll {
  overflow-y: auto;
  border: 1px solid rgba(49,51,63,0.10);
  border-radius: 10px;
  padding: 10px;
  background: rgba(248,249,251,0.75);
}

/* 질문 리스트 버튼을 '리스트 항목'처럼 */
div.stButton > button {
  text-align: left !important;
  white-space: normal !important;
  line-height: 1.25rem !important;
  padding: 10px 10px !important;
  border-radius: 10px !important;
}

/* 작은 캡션 */
.small-muted { color: rgba(49,51,63,0.55); font-size: 0.85rem; }

/* 채팅 입력바 spacing */
.chatbar {
  border: 1px solid rgba(49,51,63,0.15);
  border-radius: 12px;
  padding: 8px 8px;
  background: #fff;
}
</style>
        """,
        unsafe_allow_html=True,
    )


# =========================
# MAIN
# =========================
db_init()
ensure_state()

st.set_page_config(page_title=APP_TITLE, layout="wide")
inject_css()

st.title(APP_TITLE)

# PPT처럼 3개 패널 (좌/중/우)
col_left, col_mid, col_right = st.columns([1.1, 2.2, 2.7], gap="large")

# -------------------------
# LEFT: 작업목록
# -------------------------
with col_left:
    st.markdown('<div class="panel"><div class="panel-title">작업목록</div>', unsafe_allow_html=True)

    projects = list_projects()
    if not projects:
        st.markdown('<div class="small-muted">프로젝트가 없습니다.</div>', unsafe_allow_html=True)
    else:
        # 스크롤 박스 높이 고정 (PPT 느낌)
        with st.container(height=260, border=True):
            if not projects:
                st.caption("프로젝트가 없습니다.")
            else:
                for p in projects:
                    sel = (st.session_state["selected_project_id"] == p["id"])
                    label = f"{'✅ ' if sel else ''}{p['name']}"
                    if st.button(label, key=f"proj_{p['id']}", use_container_width=True):
                        set_project(int(p["id"]))

    st.markdown("<hr style='margin: 10px 0; opacity:0.25;'>", unsafe_allow_html=True)
    st.markdown('<div class="panel-title" style="font-size:0.95rem;">새 프로젝트</div>', unsafe_allow_html=True)

    # 위젯 값 초기화(리런 이후 처리)
    if st.session_state.get("clear_new_project_name"):
        st.session_state["new_project_name"] = ""
        st.session_state["clear_new_project_name"] = False

    new_name = st.text_input(
        "프로젝트명",
        key="new_project_name",
        label_visibility="collapsed",
        placeholder="예: 인증 로직 분석",
    )

    if st.button("프로젝트 생성", use_container_width=True):
        name = (new_name or "").strip()
        if not name:
            st.warning("프로젝트명을 입력하세요.")
        else:
            try:
                pid = create_project(name)
                set_project(pid)
                st.session_state["clear_new_project_name"] = True
                st.rerun()
            except sqlite3.IntegrityError:
                st.warning(f"이미 존재하는 프로젝트명입니다: {name}")

    st.markdown("<hr style='margin: 10px 0; opacity:0.25;'>", unsafe_allow_html=True)
    st.markdown('<div class="panel-title" style="font-size:0.95rem;">프로젝트 문서</div>', unsafe_allow_html=True)

    pid = st.session_state.get("selected_project_id")
    if not pid:
        st.caption("프로젝트를 선택하면 문서 업로드/목록이 표시됩니다.")
    else:
        up_docs = st.file_uploader(
            "문서 업로드",
            accept_multiple_files=True,
            label_visibility="collapsed",
        )
        if up_docs:
            for f in up_docs:
                save_project_doc(int(pid), f)
            st.success(f"{len(up_docs)}개 업로드 완료")
            st.rerun()

        docs = list_project_docs(int(pid))
        if not docs:
            st.caption("업로드된 문서가 없습니다.")
        else:
            with st.container(height=220, border=True):
                for d in docs:
                    c1, c2 = st.columns([4.5, 1.0], gap="small")
                    with c1:
                        st.markdown(f"**{d['filename']}**  \n{d['created_at']} · {d['size']} bytes")
                    with c2:
                        if st.button("삭제", key=f"doc_del_{d['id']}", use_container_width=True):
                            delete_project_doc(int(d["id"]))
                            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


# -------------------------
# MID: 질문리스트(위) + 채팅창(아래)
# -------------------------
with col_mid:
    st.markdown('<div class="panel"><div class="panel-title">질문리스트</div>', unsafe_allow_html=True)

    pid = st.session_state["selected_project_id"]
    if not pid:
        st.info("좌측에서 프로젝트를 선택하면 질문 리스트/채팅이 활성화됩니다.")
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        # 검색만 유지
        st.session_state["thread_search"] = st.text_input(
            "질문 검색",
            value=st.session_state["thread_search"],
            placeholder="이 프로젝트에서 질문 검색",
            label_visibility="collapsed",
        )

        # 질문 리스트(스크롤 고정) - 새 질문 버튼 없음
        threads = list_threads(int(pid), st.session_state["thread_search"])
        with st.container(height=320, border=True):
            if not threads:
                st.caption("아직 질문이 없습니다. 아래에서 전송하면 자동으로 추가됩니다.")
            else:
                for t in threads:
                    sel = (st.session_state["selected_thread_id"] == t["id"])
                    prefix = "▶ " if sel else ""
                    label = f"{prefix}{t['title']}\n\n{t['updated_at']}  [{t['tag']}]"
                    if st.button(label, key=f"th_{t['id']}", use_container_width=True):
                        set_thread(int(t["id"]))

        st.markdown("<div class='panel-title' style='margin-top:10px;'>채팅창</div>", unsafe_allow_html=True)

        # ✅ 채팅창은 '항상' 표시 (질문 선택 없어도 표시)
        selected_tid = st.session_state.get("selected_thread_id")
        turns = list_turns(int(selected_tid)) if selected_tid else []

        # 채팅 메시지 영역
        with st.container(height=260, border=True):
            if not turns:
                st.caption("대화가 없습니다.")
            else:
                for row in turns[-30:]:
                    if row["role"] == "user":
                        with st.chat_message("user"):
                            st.markdown(row["content"])
                    else:
                        with st.chat_message("assistant"):
                            c = row["content"]
                            st.markdown(c if len(c) < 1500 else (c[:1500] + "\n\n...(중략)"))

        # 입력 바: 업로드 + 입력 + 전송
      # 입력 바: 업로드(+) + 입력 + 전송  (폼으로 처리: 전송 후 입력 자동 비움)
    with st.form("chat_form", clear_on_submit=True):
        bar = st.columns([0.65, 3.4, 1.0], gap="small")

        with bar[0]:
            with st.popover("＋", use_container_width=True):
                up = st.file_uploader(
                    "파일 업로드",
                    accept_multiple_files=True,
                    label_visibility="collapsed",
                )
                if up:
                    st.session_state["upload_blobs"] = [
                        {"name": f.name, "bytes": f.getvalue(), "mime": f.type} for f in up
                    ]

        # ✅ 이게 빠져있어서 지금 아무것도 입력이 안 됐던 거임
        with bar[1]:
            msg = st.text_input(
                "추가 질문",
                placeholder="추가 질문을 입력...",
                label_visibility="collapsed",
            )

        with bar[2]:
            send = st.form_submit_button("전송", use_container_width=True)

    # 업로드 파일 표시
    if st.session_state["upload_blobs"]:
        st.caption("업로드됨: " + ", ".join([b["name"] for b in st.session_state["upload_blobs"]]))

    # ✅ 전송할 때마다 질문리스트에 새 항목(새 thread) 추가
    if send:
        msg = (msg or "").strip()
        if msg:
            # 1) 새 thread 생성 (제목은 메시지 앞부분)
            title = msg.replace("\n", " ").strip()
            if len(title) > 40:
                title = title[:40] + "..."
            new_tid = create_thread(int(pid), title=title, tag="general")

            # 2) user turn 저장
            add_turn(int(new_tid), "user", msg)

            # 3) 업로드 메타를 context로 전달(필요시)
            extra_ctx = None
            if st.session_state["upload_blobs"]:
                last = st.session_state["upload_blobs"][-1]
                upload_result = upload_to_server(last)

            # 4) LLM 호출 + 저장
            try:
                result = call_rag_api(msg, top_k=int(st.session_state["top_k"]), extra_context=extra_ctx)
                add_turn(
                    int(new_tid),
                    "assistant",
                    result.answer_markdown,
                    payload={
                        "answer_markdown": result.answer_markdown,
                        "evidence": result.evidence,
                        "artifacts": result.artifacts,
                    },
                )
            except Exception as e:
                add_turn(int(new_tid), "assistant", f"오류: {e}")

            # 5) 생성된 질문을 선택 상태로 만들고, 업로드 초기화
            set_thread(int(new_tid))
            st.session_state["upload_blobs"] = []
            st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)


# -------------------------
# RIGHT: 답변 패널
# -------------------------
with col_right:
    st.markdown('<div class="panel"><div class="panel-title">답변</div>', unsafe_allow_html=True)

    tid = st.session_state["selected_thread_id"]
    if not tid:
        st.info("질문을 선택하면 답변이 표시됩니다.")
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        turns = list_turns(int(tid))
        payload = last_assistant_payload(turns)

        if not payload:
            st.info("아직 답변이 없습니다.")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            tabs = st.tabs(["Answer", "Evidence", "Artifacts"])

            with tabs[0]:
                st.markdown(payload.get("answer_markdown", ""))

            with tabs[1]:
                ev = payload.get("evidence") or []
                if not ev:
                    st.caption("근거가 없습니다. (서버가 evidence/citations를 구조화해 내려주면 표시)")
                else:
                    for i, item in enumerate(ev, start=1):
                        title = item.get("title") or f"Evidence {i}"
                        path = item.get("path") or item.get("source") or ""
                        lines = item.get("lines") or item.get("line_range") or ""
                        snippet = item.get("snippet") or item.get("text") or ""
                        with st.expander(f"{i}. {title}  {path}  {lines}".strip()):
                            if snippet:
                                st.code(snippet)

            with tabs[2]:
                arts = payload.get("artifacts") or []
                if not arts:
                    st.caption("아티팩트가 없습니다.")
                else:
                    for i, a in enumerate(arts, start=1):
                        a_type = a.get("type", "artifact")
                        a_title = a.get("title", f"{a_type} {i}")
                        content = a.get("content", "")
                        st.markdown(f"**{a_title}**  (`{a_type}`)")
                        st.code(content)

    st.markdown("</div>", unsafe_allow_html=True)