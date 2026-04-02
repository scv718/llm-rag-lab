import unittest

from app.services.search_services import (
    build_context_and_citations,
    extract_search_keywords,
    extract_symbol_hints,
    rerank_search_results,
)


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


if __name__ == "__main__":
    unittest.main()
