import streamlit as st

from app.db.turn_repo import list_turns
from app.utils.payload import last_assistant_payload


def render_right_panel():

    st.markdown('<div class="panel"><div class="panel-title">답변</div>', unsafe_allow_html=True)

    tid = st.session_state["selected_thread_id"]

    if not tid:
        st.info("질문을 선택하세요.")
        return

    turns = list_turns(tid)

    payload = last_assistant_payload(turns)

    if not payload:
        st.info("아직 답변이 없습니다.")
        return

    tabs = st.tabs(["Answer", "Evidence", "Artifacts"])

    with tabs[0]:
        st.markdown(payload.get("answer_markdown", ""))

    with tabs[1]:

        for ev in payload.get("evidence", []):

            with st.expander(ev.get("title", "Evidence")):
                st.code(ev.get("snippet", ""))

    with tabs[2]:

        for art in payload.get("artifacts", []):

            st.code(art.get("content", ""))

    st.markdown("</div>", unsafe_allow_html=True)