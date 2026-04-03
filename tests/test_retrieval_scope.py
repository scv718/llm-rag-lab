import unittest
from pathlib import Path

from app.services.project_scope import build_project_scope


class RetrievalScopeTest(unittest.TestCase):
    def test_build_project_scope_for_whole_project(self):
        where, repo_dirs = build_project_scope(
            3,
            False,
            [],
            [{"doc_id": "doc-1"}, {"doc_id": "doc-2"}],
            [{"repo_id": "repo-1"}],
            Path("/tmp/repos"),
        )

        self.assertEqual(2, len(where["$or"]))
        self.assertEqual(["doc-1", "doc-2"], where["$or"][0]["$and"][1]["doc_id"]["$in"])
        self.assertEqual(["repo-1"], where["$or"][1]["$and"][1]["repo_id"]["$in"])
        self.assertEqual(1, len(repo_dirs))

    def test_build_project_scope_for_active_targets_only(self):
        where, repo_dirs = build_project_scope(
            5,
            True,
            [
                {"target_kind": "doc", "target_ref_id": "doc-2"},
                {"target_kind": "code", "target_ref_id": "repo-1"},
            ],
            [{"doc_id": "doc-1"}, {"doc_id": "doc-2"}],
            [{"repo_id": "repo-1"}, {"repo_id": "repo-2"}],
            Path("/tmp/repos"),
        )

        self.assertEqual(2, len(where["$or"]))
        self.assertEqual(["doc-2"], where["$or"][0]["$and"][1]["doc_id"]["$in"])
        self.assertEqual(["repo-1"], where["$or"][1]["$and"][1]["repo_id"]["$in"])
        self.assertEqual(1, len(repo_dirs))


if __name__ == "__main__":
    unittest.main()
