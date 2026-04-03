import hashlib

import streamlit as st

from app.db.doc_repo import (
    delete_project_doc,
    list_project_docs,
    save_project_doc_blob,
)
from app.db.repo_repo import (
    delete_project_repo,
    list_project_repos,
    save_project_repo_blob,
)
from app.db.project_repo import create_project, list_projects
from app.db.target_repo import (
    clear_project_target,
    get_project_target,
    upsert_project_target,
)
from app.services.upload_client import upload_to_server_for_project


def file_hash(file):
    return hashlib.sha256(file.getvalue()).hexdigest()


def render_left_panel(set_project, _unused=None):
    uploaded_files_by_project = st.session_state.setdefault("uploaded_files_by_project", {})

    st.markdown('<div class="panel"><div class="panel-title">작업목록</div>', unsafe_allow_html=True)

    projects = list_projects()

    if not projects:
        st.caption("프로젝트가 없습니다.")
    else:
        with st.container(height=260, border=True):
            for project in projects:
                selected = st.session_state["selected_project_id"] == project["id"]
                label = f"{'✅ ' if selected else ''}{project['name']}"

                if st.button(label, key=f"proj_{project['id']}", use_container_width=True):
                    set_project(int(project["id"]))

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
            project_id = create_project(name)
            set_project(project_id)
            st.rerun()

    st.markdown("<hr style='margin: 10px 0; opacity:0.25;'>", unsafe_allow_html=True)

    project_id = st.session_state.get("selected_project_id")

    with st.expander("📦 프로젝트 자산", expanded=False):
        if not project_id:
            st.caption("프로젝트를 선택하면 자산이 표시됩니다.")
            return

        project_hashes = uploaded_files_by_project.setdefault(project_id, set())
        target = get_project_target(project_id)

        if target:
            st.caption(f"활성 타깃: `{target['target_kind']}` / `{target['filename']}`")
        else:
            st.caption("활성 타깃이 없습니다. 업로드하거나 목록에서 선택하세요.")

        uploads = st.file_uploader(
            "문서 또는 코드 업로드",
            accept_multiple_files=True,
            label_visibility="collapsed",
            key=f"asset_uploader_{project_id}",
        )
        st.caption("지원 형식: pdf, zip, txt, md, docx, xlsx, csv, java, py, js, ts, xml, yml, yaml, sql")

        if uploads:
            uploaded_count = 0

            for file in uploads:
                file_sha = file_hash(file)
                if file_sha in project_hashes:
                    continue

                raw = file.getvalue()
                response = upload_to_server_for_project(
                    {
                        "name": file.name,
                        "bytes": raw,
                        "mime": file.type,
                    },
                    project_id=project_id,
                )

                if response["kind"] == "doc":
                    save_project_doc_blob(
                        project_id=project_id,
                        filename=file.name,
                        raw=raw,
                        mime=file.type,
                        doc_id=response["doc_id"],
                    )
                    upsert_project_target(project_id, "doc", response["doc_id"], file.name)
                else:
                    save_project_repo_blob(
                        project_id=project_id,
                        filename=file.name,
                        raw=raw,
                        repo_id=response["repo_id"],
                        extract_path=response["extract_path"],
                    )
                    upsert_project_target(project_id, "code", response["repo_id"], file.name)

                project_hashes.add(file_sha)
                uploaded_count += 1

            if uploaded_count > 0:
                st.success(f"{uploaded_count}개 업로드 완료")
                st.rerun()

        docs = list_project_docs(project_id)
        repos = list_project_repos(project_id)

        st.markdown("**문서**")
        if not docs:
            st.caption("업로드된 문서가 없습니다.")

        for doc in docs:
            render_asset_row(
                label=f"📄 {doc['filename']}",
                row_id=int(doc["id"]),
                select_key=f"doc_sel_{doc['id']}",
                delete_key=f"doc_del_{doc['id']}",
                is_active=is_active_target(target, "doc", doc["doc_id"]),
                on_select=lambda doc_id=doc["doc_id"], filename=doc["filename"]: upsert_project_target(
                    project_id,
                    "doc",
                    doc_id,
                    filename,
                ),
                on_delete=lambda row_id=int(doc["id"]), doc_id=doc["doc_id"]: delete_doc_asset(
                    project_id,
                    row_id,
                    target,
                    doc_id,
                ),
            )

        st.markdown("**코드**")
        if not repos:
            st.caption("업로드된 코드 자산이 없습니다.")

        for repo in repos:
            render_asset_row(
                label=f"🧩 {repo['filename']}",
                row_id=int(repo["id"]),
                select_key=f"repo_sel_{repo['id']}",
                delete_key=f"repo_del_{repo['id']}",
                is_active=is_active_target(target, "code", repo["repo_id"]),
                on_select=lambda repo_id=repo["repo_id"], filename=repo["filename"]: upsert_project_target(
                    project_id,
                    "code",
                    repo_id,
                    filename,
                ),
                on_delete=lambda row_id=int(repo["id"]), repo_id=repo["repo_id"]: delete_repo_asset(
                    project_id,
                    row_id,
                    target,
                    repo_id,
                ),
            )

    st.markdown("</div>", unsafe_allow_html=True)


def render_asset_row(label, row_id, select_key, delete_key, is_active, on_select, on_delete):
    c1, c2, c3 = st.columns([4.0, 1.2, 1.0])

    with c1:
        suffix = " `active`" if is_active else ""
        st.markdown(f"{label}{suffix}")

    with c2:
        if st.button("선택", key=select_key, use_container_width=True):
            on_select()
            st.rerun()

    with c3:
        if st.button("삭제", key=delete_key, use_container_width=True):
            on_delete()
            st.rerun()


def is_active_target(target, kind, ref_id):
    return bool(
        target
        and target["target_kind"] == kind
        and target["target_ref_id"] == ref_id
    )


def delete_doc_asset(project_id, row_id, target, doc_id):
    delete_project_doc(row_id)
    if is_active_target(target, "doc", doc_id):
        clear_project_target(project_id)


def delete_repo_asset(project_id, row_id, target, repo_id):
    delete_project_repo(row_id)
    if is_active_target(target, "code", repo_id):
        clear_project_target(project_id)
