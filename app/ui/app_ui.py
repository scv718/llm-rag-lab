import streamlit as st

from app.db.doc_repo import save_project_doc
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


def set_project(pid: int):

    st.session_state["selected_project_id"] = pid
    st.session_state["selected_thread_id"] = None


def set_thread(tid: int):

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
    render_left_panel(set_project, save_project_doc)

with col_mid:
    render_mid_panel(set_thread)

with col_right:
    render_right_panel()