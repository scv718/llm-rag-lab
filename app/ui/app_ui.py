import sys
from pathlib import Path

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db.database import db_init

from app.ui.components.left_panel import render_left_panel
from app.ui.components.mid_panel import render_mid_panel
from app.ui.components.right_panel import render_right_panel


APP_TITLE = "RAG Q/A Tool"


# -------------------------
# session helpers
# -------------------------
def ensure_state():

    st.session_state.setdefault("selected_project_id", None)
    st.session_state.setdefault("selected_thread_id", None)
    st.session_state.setdefault("upload_blobs", [])
    st.session_state.setdefault("selected_llm_provider", "gemini")
    st.session_state.setdefault("selected_llm_model", "")
    st.session_state.setdefault("selected_llm_provider_ui", st.session_state["selected_llm_provider"])


def set_project(pid: int | None):

    st.session_state["selected_project_id"] = pid
    st.session_state["selected_thread_id"] = None


def set_thread(tid: int | None):

    st.session_state["selected_thread_id"] = tid


# -------------------------
# APP START
# -------------------------
db_init()

st.set_page_config(
    page_title=APP_TITLE,
    layout="wide"
)

ensure_state()

st.title(APP_TITLE)


# -------------------------
# layout
# -------------------------
col_left, col_mid, col_right = st.columns([1.1, 2.2, 2.7], gap="large")


with col_left:
    render_left_panel(set_project, None)

with col_mid:
    render_mid_panel(set_thread)

with col_right:
    render_right_panel()
