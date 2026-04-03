from pathlib import Path


def build_project_scope(project_id: int, active_only: bool, active_targets: list, docs: list, repos: list, repo_dir: Path) -> tuple[dict, list]:
    if active_only:
        allowed_doc_ids = {row["target_ref_id"] for row in active_targets if row["target_kind"] == "doc"}
        allowed_repo_ids = {row["target_ref_id"] for row in active_targets if row["target_kind"] == "code"}
        docs = [doc for doc in docs if doc["doc_id"] in allowed_doc_ids]
        repos = [repo for repo in repos if repo["repo_id"] in allowed_repo_ids]

    clauses = []
    if docs:
        clauses.append({"$and": [{"kind": "doc"}, {"doc_id": {"$in": [doc["doc_id"] for doc in docs]}}]})
    if repos:
        clauses.append({"$and": [{"kind": "code"}, {"repo_id": {"$in": [repo["repo_id"] for repo in repos]}}]})

    repo_extract_dirs = [repo_dir / repo["repo_id"] for repo in repos]

    if not clauses:
        return {"$and": [{"kind": "__none__"}]}, []
    if len(clauses) == 1:
        return clauses[0], repo_extract_dirs
    return {"$or": clauses}, repo_extract_dirs
