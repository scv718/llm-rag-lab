import streamlit as st

from app.core.config import LLM_MODEL, LOCAL_LLM_MODEL
from app.db.turn_repo import list_turns
from app.utils.payload import last_assistant_payload


LLM_PROVIDER_OPTIONS = {
    "gemini": {
        "label": "Gemini",
        "default_model": LLM_MODEL,
        "help": "기본 Gemini API 설정을 사용합니다.",
    },
    "local": {
        "label": "Local (Ollama/OpenAI-Compatible)",
        "default_model": LOCAL_LLM_MODEL,
        "help": "OPENAI_BASE_URL 기준의 로컬 LLM 서버를 사용합니다.",
    },
}


def render_right_panel():

    st.markdown('<div class="panel"><div class="panel-title">답변</div>', unsafe_allow_html=True)
    render_llm_selector()

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
            title = build_evidence_title(ev)
            with st.expander(title):
                st.json(ev)

    with tabs[2]:

        for art in payload.get("artifacts", []):
            label = art.get("label", "artifact")
            with st.expander(label, expanded=False):
                st.code(art.get("content", ""), language="json")

    st.markdown("</div>", unsafe_allow_html=True)


def render_llm_selector():
    options = list(LLM_PROVIDER_OPTIONS.keys())
    current_provider = st.session_state.get("selected_llm_provider", "gemini")
    if current_provider not in LLM_PROVIDER_OPTIONS:
        current_provider = "gemini"

    if st.session_state.get("selected_llm_provider_ui") not in LLM_PROVIDER_OPTIONS:
        st.session_state["selected_llm_provider_ui"] = current_provider

    st.selectbox(
        "LLM Provider",
        options=options,
        index=options.index(current_provider),
        format_func=lambda key: LLM_PROVIDER_OPTIONS[key]["label"],
        key="selected_llm_provider_ui",
        help="질문을 보낼 때 사용할 모델 제공자를 선택합니다.",
    )

    selected_provider = st.session_state["selected_llm_provider_ui"]

    default_model = LLM_PROVIDER_OPTIONS[selected_provider]["default_model"]
    if st.session_state.get("selected_llm_provider") != selected_provider:
        st.session_state["selected_llm_provider"] = selected_provider
        st.session_state["selected_llm_model"] = default_model
    elif not st.session_state.get("selected_llm_model", "").strip():
        st.session_state["selected_llm_model"] = default_model

    st.text_input(
        "Model",
        key="selected_llm_model",
        help=LLM_PROVIDER_OPTIONS[selected_provider]["help"],
        placeholder=default_model,
    )


def build_evidence_title(ev):
    kind = ev.get("kind", "evidence")

    if kind == "code":
        path = ev.get("path", ev.get("filename", "unknown"))
        return f"code · {path} · L{ev.get('start_line', '?')}-L{ev.get('end_line', '?')}"

    if kind == "doc":
        filename = ev.get("filename", "document")
        return f"doc · {filename} · page {ev.get('page', '?')}"

    if kind == "keyword":
        return f"keyword · {ev.get('path', 'unknown')} · line {ev.get('line', '?')}"

    if kind == "path":
        return f"path · {ev.get('path', 'unknown')}"

    return "Evidence"
