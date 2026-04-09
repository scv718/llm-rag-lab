import streamlit as st
import requests

from app.db.thread_repo import list_threads, create_thread, delete_thread
from app.db.turn_repo import add_turn, list_turns
from app.services.rag_client import call_rag_api


def render_mid_panel(set_thread):

    pid = st.session_state["selected_project_id"]

    if not pid:
        st.info("좌측에서 프로젝트를 선택하세요.")
        return

    st.markdown('<div class="panel"><div class="panel-title">질문리스트</div>', unsafe_allow_html=True)

    threads = list_threads(pid)
    tid = st.session_state.get("selected_thread_id")
    llm_provider = st.session_state.get("selected_llm_provider", "gemini")
    llm_model = st.session_state.get("selected_llm_model", "").strip()

    top_col1, top_col2 = st.columns([1.2, 2.8])
    with top_col1:
        if st.button("새 질문", use_container_width=True):
            set_thread(None)
            st.rerun()
    with top_col2:
        if tid:
            st.caption("현재 선택된 질문에 이어서 대화 중")
        else:
            st.caption("새 질문을 입력하면 새 스레드가 생성됩니다")

    with st.container(height=320, border=True):

        for t in threads:
            col1, col2 = st.columns([4.0, 1.0])
            with col1:
                if st.button(t["title"], key=f"th_{t['id']}", use_container_width=True):
                    set_thread(int(t["id"]))
            with col2:
                if st.button("삭제", key=f"th_del_{t['id']}", use_container_width=True):
                    if tid == int(t["id"]):
                        set_thread(None)
                    delete_thread(int(t["id"]))
                    st.rerun()

    st.markdown("<div class='panel-title'>채팅창</div>", unsafe_allow_html=True)
    st.caption(f"현재 LLM: `{llm_provider}`" + (f" / `{llm_model}`" if llm_model else ""))

    turns = list_turns(tid) if tid else []

    with st.container(height=260, border=True):

        for row in turns[-30:]:

            with st.chat_message(row["role"]):
                st.markdown(row["content"])

    msg = st.chat_input("질문 입력")

    if msg:
        current_tid = tid or create_thread(pid, msg[:40])

        add_turn(current_tid, "user", msg)

        try:
            result = call_rag_api(
                msg,
                5,
                project_id=pid,
                llm_provider=llm_provider,
                llm_model=llm_model or None,
            )
        except requests.HTTPError as exc:
            detail = exc.response.text if exc.response is not None else str(exc)
            add_turn(current_tid, "assistant", f"요청 실패: {detail}")
            set_thread(current_tid)
            st.error("RAG API 요청에 실패했습니다.")
            st.rerun()
        except Exception as exc:
            add_turn(current_tid, "assistant", f"처리 실패: {exc}")
            set_thread(current_tid)
            st.error("질문 처리 중 오류가 발생했습니다.")
            st.rerun()

        add_turn(
            current_tid,
            "assistant",
            result.answer_markdown,
            payload={
                "answer_markdown": result.answer_markdown,
                "evidence": result.evidence,
                "artifacts": result.artifacts,
            }
        )

        set_thread(current_tid)

        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
