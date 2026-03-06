import streamlit as st
import hashlib

from app.db.project_repo import list_projects, create_project
from app.db.doc_repo import list_project_docs, delete_project_doc
from app.services.upload_client import upload_to_server


def file_hash(file):
    return hashlib.sha256(file.getvalue()).hexdigest()


def render_left_panel(set_project, save_project_doc):

    # 업로드된 파일 해시 저장용
    if "uploaded_files" not in st.session_state:
        st.session_state["uploaded_files"] = set()

    st.markdown('<div class="panel"><div class="panel-title">작업목록</div>', unsafe_allow_html=True)

    projects = list_projects()

    if not projects:
        st.caption("프로젝트가 없습니다.")
    else:

        with st.container(height=260, border=True):

            for p in projects:

                sel = (st.session_state["selected_project_id"] == p["id"])
                label = f"{'✅ ' if sel else ''}{p['name']}"

                if st.button(label, key=f"proj_{p['id']}", use_container_width=True):
                    set_project(int(p["id"]))

    st.markdown("<hr style='margin: 10px 0; opacity:0.25;'>", unsafe_allow_html=True)

    new_name = st.text_input(
        "프로젝트명",
        key="new_project_name",
        label_visibility="collapsed",
        placeholder="예: 인증 로직 분석",
    )

    if st.button("프로젝트 생성", use_container_width=True):

        name = (new_name or "").strip()

        if name:

            pid = create_project(name)

            set_project(pid)

            st.rerun()

    st.markdown("<hr style='margin: 10px 0; opacity:0.25;'>", unsafe_allow_html=True)

    pid = st.session_state.get("selected_project_id")

    with st.expander("📂 프로젝트 문서", expanded=False):

        if not pid:
            st.caption("프로젝트를 선택하면 문서가 표시됩니다.")
            return

        up_docs = st.file_uploader(
            "문서 업로드",
            accept_multiple_files=True,
            label_visibility="collapsed",
            key="doc_uploader"
        )

        if up_docs:

            uploaded_count = 0

            for f in up_docs:

                h = file_hash(f)

                # 이미 업로드된 파일이면 skip
                if h in st.session_state["uploaded_files"]:
                    continue

                # 로컬 DB 저장
                save_project_doc(pid, f)

                # 서버 업로드
                upload_to_server({
                    "name": f.name,
                    "bytes": f.getvalue(),
                    "mime": f.type
                })

                st.session_state["uploaded_files"].add(h)
                uploaded_count += 1

            if uploaded_count > 0:
                st.success(f"{uploaded_count}개 업로드 완료")
                st.rerun()

        docs = list_project_docs(pid)

        for d in docs:

            c1, c2 = st.columns([4.5, 1])

            with c1:
                st.markdown(f"📄 **{d['filename']}**")

            with c2:
                if st.button("삭제", key=f"doc_del_{d['id']}"):
                    delete_project_doc(int(d["id"]))
                    st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)