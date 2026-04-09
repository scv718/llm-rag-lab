import hashlib

import streamlit as st
from app.db import project_repo

from app.db.doc_repo import (
    delete_project_doc,
    list_project_docs,
)
from app.db.repo_repo import (
    delete_project_repo,
    list_project_repos,
)
from app.db.target_repo import (
    add_project_target,
    get_project_target_settings,
    list_project_targets,
    remove_project_target,
    set_project_targeting_mode,
)
from app.services.upload_client import upload_to_server_for_project


def file_hash(file):
    return hashlib.sha256(file.getvalue()).hexdigest()


def render_left_panel(set_project, _unused=None):
    uploaded_files_by_project = st.session_state.setdefault("uploaded_files_by_project", {})

    st.markdown('<div class="panel"><div class="panel-title">작업목록</div>', unsafe_allow_html=True)

    projects = project_repo.list_projects()

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
            project_id = project_repo.create_project(name)
            set_project(project_id)
            st.rerun()

    st.markdown("<hr style='margin: 10px 0; opacity:0.25;'>", unsafe_allow_html=True)

    project_id = st.session_state.get("selected_project_id")

    if project_id:
        action_col1, action_col2 = st.columns([2.2, 1.0])
        with action_col1:
            st.caption(f"선택된 프로젝트: `{project_id}`")
        with action_col2:
            if st.button("프로젝트 삭제", key=f"delete_project_{project_id}", use_container_width=True):
                project_repo.delete_project(project_id)
                uploaded_files_by_project.pop(project_id, None)
                set_project(None)
                st.rerun()

    with st.expander("📦 프로젝트 자산", expanded=False):
        if not project_id:
            st.caption("프로젝트를 선택하면 자산이 표시됩니다.")
            return

        project_hashes = uploaded_files_by_project.setdefault(project_id, set())
        active_targets = list_project_targets(project_id)
        active_target_keys = {(row["target_kind"], row["target_ref_id"]) for row in active_targets}
        target_settings = get_project_target_settings(project_id)
        active_only_default = bool(target_settings["active_only"]) if target_settings else False

        active_only = st.checkbox(
            "Use active selection only",
            value=active_only_default,
            key=f"active_only_{project_id}",
        )
        if active_only != active_only_default:
            set_project_targeting_mode(project_id, active_only)

        if active_only:
            if active_targets:
                st.caption(f"활성 자산만 검색 중: {len(active_targets)}개 선택됨")
            else:
                st.caption("활성 자산 검색이 켜져 있습니다. 아래에서 자산을 선택하세요.")
        else:
            st.caption("전체검색 중입니다. 활성 자산을 선택해 두면 필요할 때만 좁혀서 검색할 수 있습니다.")

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
                toggle_key=f"doc_tog_{doc['id']}",
                delete_key=f"doc_del_{doc['id']}",
                is_active=is_active_target(active_target_keys, "doc", doc["doc_id"]),
                on_toggle=lambda doc_id=doc["doc_id"], filename=doc["filename"]: toggle_target(
                    project_id,
                    "doc",
                    doc_id,
                    filename,
                    active_target_keys,
                ),
                on_delete=lambda row_id=int(doc["id"]), doc_id=doc["doc_id"]: delete_doc_asset(
                    project_id,
                    row_id,
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
                toggle_key=f"repo_tog_{repo['id']}",
                delete_key=f"repo_del_{repo['id']}",
                is_active=is_active_target(active_target_keys, "code", repo["repo_id"]),
                on_toggle=lambda repo_id=repo["repo_id"], filename=repo["filename"]: toggle_target(
                    project_id,
                    "code",
                    repo_id,
                    filename,
                    active_target_keys,
                ),
                on_delete=lambda row_id=int(repo["id"]), repo_id=repo["repo_id"]: delete_repo_asset(
                    project_id,
                    row_id,
                    repo_id,
                ),
            )

    st.markdown("</div>", unsafe_allow_html=True)


def render_asset_row(label, row_id, toggle_key, delete_key, is_active, on_toggle, on_delete):
    c1, c2, c3 = st.columns([4.0, 1.2, 1.0])

    with c1:
        suffix = " `active`" if is_active else ""
        st.markdown(f"{label}{suffix}")

    with c2:
        button_label = "해제" if is_active else "활성"
        if st.button(button_label, key=toggle_key, use_container_width=True):
            on_toggle()
            st.rerun()

    with c3:
        if st.button("삭제", key=delete_key, use_container_width=True):
            on_delete()
            st.rerun()


def is_active_target(active_target_keys, kind, ref_id):
    return (kind, ref_id) in active_target_keys


def toggle_target(project_id, kind, ref_id, filename, active_target_keys):
    if (kind, ref_id) in active_target_keys:
        remove_project_target(project_id, kind, ref_id)
    else:
        add_project_target(project_id, kind, ref_id, filename)


def delete_doc_asset(project_id, row_id, doc_id):
    delete_project_doc(row_id)
    remove_project_target(project_id, "doc", doc_id)


def delete_repo_asset(project_id, row_id, repo_id):
    delete_project_repo(row_id)
    remove_project_target(project_id, "code", repo_id)
