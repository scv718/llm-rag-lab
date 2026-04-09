import unittest

from app.services.search_services import (
    build_context_and_citations,
    extract_search_keywords,
    extract_symbol_hints,
    keyword_search_in_repo,
    merge_search_results,
    rerank_search_results,
)
from app.services.retrieval import keyword_search as keyword_search_module
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


class SearchServicesTest(unittest.TestCase):
    def test_extract_search_keywords_keeps_path_and_symbol(self):
        keywords = extract_search_keywords("`AuthController`에서 /api/login 처리 위치 알려줘")
        self.assertIn("AuthController", keywords)
        self.assertIn("/api/login", keywords)

    def test_extract_symbol_hints_finds_code_symbols(self):
        hints = extract_symbol_hints("UserService와 AUTH_TOKEN 사용 위치 찾아줘")
        self.assertIn("UserService", hints)
        self.assertIn("AUTH_TOKEN", hints)

    def test_rerank_prefers_symbol_and_path_matches(self):
        merged_hits = [
            {
                "source": "vector",
                "metadata": {
                    "kind": "code",
                    "path": "auth/controller/AuthController.java",
                    "start_line": 10,
                    "end_line": 40,
                    "chunk_id": "chunk-1",
                    "filename": "demo.zip",
                },
                "document": "public class AuthController { @PostMapping(\"/api/login\") }",
                "distance": 0.21,
            },
            {
                "source": "vector",
                "metadata": {
                    "kind": "code",
                    "path": "user/service/ProfileService.java",
                    "start_line": 1,
                    "end_line": 30,
                    "chunk_id": "chunk-2",
                    "filename": "demo.zip",
                },
                "document": "public class ProfileService { }",
                "distance": 0.19,
            },
        ]

        ranked = rerank_search_results(
            question="AuthController에서 /api/login 처리 위치 알려줘",
            keywords=["AuthController", "/api/login"],
            symbol_hints=["AuthController"],
            merged_hits=merged_hits,
            limit=5,
        )

        self.assertEqual("auth/controller/AuthController.java", ranked[0]["metadata"]["path"])

    def test_build_context_and_citations_keeps_score(self):
        ranked_hits = [
            {
                "source": "keyword",
                "path": "auth/controller/AuthController.java",
                "line": 42,
                "text": "@PostMapping(\"/api/login\")",
                "matched_keywords": ["/api/login"],
                "score": 4.5,
            }
        ]

        context, citations = build_context_and_citations(ranked_hits)
        self.assertIn("score=4.5", context)
        self.assertEqual(4.5, citations[0]["score"])

    def test_build_context_and_citations_merges_adjacent_code_hits(self):
        ranked_hits = [
            {
                "source": "vector",
                "metadata": {
                    "kind": "code",
                    "source_type": "zip",
                    "path": "auth/AuthController.java",
                    "start_line": 10,
                    "end_line": 20,
                    "chunk_id": "chunk-1",
                },
                "document": "line 10\nline 20",
                "distance": 0.2,
                "score": 3.5,
            },
            {
                "source": "vector",
                "metadata": {
                    "kind": "code",
                    "source_type": "zip",
                    "path": "auth/AuthController.java",
                    "start_line": 21,
                    "end_line": 30,
                    "chunk_id": "chunk-2",
                },
                "document": "line 21\nline 30",
                "distance": 0.18,
                "score": 3.7,
            },
        ]

        context, citations = build_context_and_citations(ranked_hits)
        self.assertEqual(1, len(citations))
        self.assertIn("L10-L30", context)

    def test_build_context_and_citations_respects_context_budget(self):
        ranked_hits = [
            {
                "source": "keyword",
                "path": "auth/controller/AuthController.java",
                "line": 42,
                "text": "x" * 500,
                "matched_keywords": ["/api/login"],
                "score": 4.5,
            },
            {
                "source": "keyword",
                "path": "auth/service/AuthService.java",
                "line": 84,
                "text": "y" * 500,
                "matched_keywords": ["login"],
                "score": 4.0,
            },
        ]

        context, citations = build_context_and_citations(ranked_hits, max_context_chars=700)
        self.assertEqual(1, len(citations))

    def test_keyword_search_in_repo_includes_path_hits(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "alarm" / "service" / "AlarmServiceImpl.java"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("public class AlarmServiceImpl {}", encoding="utf-8")

            hits = keyword_search_in_repo(root, ["AlarmServiceImpl"], limit=10)

            self.assertEqual("path", hits[0]["source"])
            self.assertIn("alarm/service/AlarmServiceImpl.java", hits[0]["path"])

    def test_keyword_search_path_listing_is_cached_between_calls(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "alarm" / "service" / "AlarmServiceImpl.java"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("public class AlarmServiceImpl {}", encoding="utf-8")

            keyword_search_module._list_repo_code_paths_cached.cache_clear()

            real_run = keyword_search_module.subprocess.run
            rg_files_calls = 0

            def counting_run(*args, **kwargs):
                nonlocal rg_files_calls
                cmd = args[0]
                if len(cmd) >= 2 and cmd[0] == "rg" and cmd[1] == "--files":
                    rg_files_calls += 1
                return real_run(*args, **kwargs)

            with patch.object(keyword_search_module.subprocess, "run", side_effect=counting_run):
                first_hits = keyword_search_in_repo(root, ["AlarmServiceImpl"], limit=10)
                second_hits = keyword_search_in_repo(root, ["AlarmServiceImpl"], limit=10)

            self.assertEqual(1, rg_files_calls)
            self.assertEqual(first_hits, second_hits)

    def test_keyword_search_path_hits_support_identifier_split_matching(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "alarm" / "service" / "alarm_service_impl.java"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("class AlarmServiceImpl {}", encoding="utf-8")

            hits = keyword_search_in_repo(root, ["AlarmServiceImpl"], limit=10)

            self.assertEqual("path", hits[0]["source"])
            self.assertEqual("alarm/service/alarm_service_impl.java", hits[0]["path"])

    def test_keyword_search_path_hits_support_compound_path_keywords(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "auth" / "controller" / "LoginController.java"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("class LoginController {}", encoding="utf-8")

            hits = keyword_search_in_repo(root, ["auth/controller/LoginController"], limit=10)

            self.assertEqual("path", hits[0]["source"])
            self.assertEqual("auth/controller/LoginController.java", hits[0]["path"])

    def test_rerank_prefers_path_hits_for_structure_queries(self):
        merged_hits = [
            {
                "source": "path",
                "path": "alarm/service/AlarmServiceImpl.java",
                "line": 0,
                "text": "alarm/service/AlarmServiceImpl.java",
                "matched_keywords": ["AlarmServiceImpl"],
            },
            {
                "source": "vector",
                "metadata": {
                    "kind": "code",
                    "path": "misc/Helper.java",
                    "start_line": 1,
                    "end_line": 5,
                    "chunk_id": "chunk-3",
                    "filename": "demo.zip",
                },
                "document": "public class Helper {}",
                "distance": 0.2,
            },
        ]

        ranked = rerank_search_results(
            question="프로젝트 구조 알려줘 AlarmServiceImpl 기준으로",
            keywords=["AlarmServiceImpl"],
            symbol_hints=["AlarmServiceImpl"],
            merged_hits=merged_hits,
            limit=5,
        )

        self.assertEqual("path", ranked[0]["source"])

    def test_rerank_prefers_code_hits_for_non_structure_queries(self):
        merged_hits = [
            {
                "source": "path",
                "path": "dto/SmsTcpMsgBean.java",
                "line": 0,
                "text": "dto/SmsTcpMsgBean.java",
                "matched_keywords": ["SmsTcpMsgBean"],
            },
            {
                "source": "keyword",
                "path": "dto/SmsTcpMsgBean.java",
                "line": 54,
                "text": "private SmsTcpObjectBean reqBean;",
                "matched_keywords": ["SmsTcpObjectBean"],
            },
            {
                "source": "vector",
                "metadata": {
                    "kind": "code",
                    "path": "dto/SmsTcpMsgBean.java",
                    "start_line": 40,
                    "end_line": 70,
                    "chunk_id": "chunk-4",
                    "filename": "demo.zip",
                },
                "document": "private SmsTcpObjectBean reqBean;\nprivate SmsTcpObjectBean resBean;",
                "distance": 0.18,
            },
        ]

        ranked = rerank_search_results(
            question="TCP 관련된 부분 설명해줘",
            keywords=["SmsTcpObjectBean", "SmsTcpMsgBean"],
            symbol_hints=["SmsTcpObjectBean", "SmsTcpMsgBean"],
            merged_hits=merged_hits,
            limit=5,
        )

        self.assertNotEqual("path", ranked[0]["source"])

    def test_rerank_prefers_semantic_code_for_general_questions(self):
        merged_hits = [
            {
                "source": "path",
                "path": "auth/controller/AuthController.java",
                "line": 0,
                "text": "auth/controller/AuthController.java",
                "matched_keywords": ["AuthController"],
            },
            {
                "source": "vector",
                "metadata": {
                    "kind": "code",
                    "path": "auth/service/AuthService.java",
                    "start_line": 1,
                    "end_line": 20,
                    "chunk_id": "chunk-5",
                    "filename": "demo.zip",
                },
                "document": "로그인 요청을 검증하고 토큰을 발급하는 서비스 로직",
                "distance": 0.12,
            },
        ]

        ranked = rerank_search_results(
            question="로그인 처리 로직 설명해줘",
            keywords=["로그인", "토큰"],
            symbol_hints=[],
            merged_hits=merged_hits,
            limit=5,
        )

        self.assertEqual("vector", ranked[0]["source"])

    def test_merge_search_results_drops_path_hit_when_content_exists_for_same_file(self):
        keyword_hits = [
            {
                "source": "path",
                "path": "dto/SmsTcpMsgBean.java",
                "line": 0,
                "text": "dto/SmsTcpMsgBean.java",
                "matched_keywords": ["SmsTcpMsgBean"],
            },
            {
                "source": "keyword",
                "path": "dto/SmsTcpMsgBean.java",
                "line": 54,
                "text": "private SmsTcpObjectBean reqBean;",
                "matched_keywords": ["SmsTcpObjectBean"],
            },
        ]
        vector_hits = []

        merged = merge_search_results(keyword_hits, vector_hits)

        self.assertEqual(1, len(merged))
        self.assertEqual("keyword", merged[0]["source"])


if __name__ == "__main__":
    unittest.main()
