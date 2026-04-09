import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.chunking import chunk_text_by_chars
from app.services.zip_ingest import chunk_code_by_lines, decode_text_best_effort, extract_text_from_path
from app.utils.file_utils import detect_file_kind


class FileTypeSupportTest(unittest.TestCase):
    def test_detects_supported_document_types(self):
        self.assertEqual("pdf", detect_file_kind(b"%PDF-1.7 sample", "sample.pdf"))
        self.assertEqual("txt", detect_file_kind(b"hello", "notes.txt"))
        self.assertEqual("md", detect_file_kind(b"# title", "README.md"))
        self.assertEqual("csv", detect_file_kind(b"id,name\n1,Alice", "users.csv"))
        self.assertEqual("docx", detect_file_kind(b"PK\x03\x04content", "spec.docx"))
        self.assertEqual("xlsx", detect_file_kind(b"PK\x03\x04content", "sheet.xlsx"))

    def test_detects_single_code_files(self):
        for filename in ("App.java", "main.py", "api.js", "route.ts", "mapper.xml", "config.yml", "query.sql"):
            with self.subTest(filename=filename):
                self.assertEqual("code", detect_file_kind(b"print('ok')", filename))

    def test_decode_text_best_effort_supports_utf8_and_cp949(self):
        self.assertEqual("hello", decode_text_best_effort("hello".encode("utf-8")))
        self.assertEqual("테스트", decode_text_best_effort("테스트".encode("cp949")))

    def test_markdown_and_csv_can_be_chunked_as_documents(self):
        md_chunks = chunk_text_by_chars(doc_id="doc-1", page=1, text="# Title\n\nBody text", chunk_size=20, overlap=5)
        csv_chunks = chunk_text_by_chars(doc_id="doc-2", page=1, text="row 2 | id: 1 | name: Alice", chunk_size=30, overlap=5)

        self.assertGreaterEqual(len(md_chunks), 1)
        self.assertGreaterEqual(len(csv_chunks), 1)

    def test_single_code_files_can_be_chunked(self):
        chunks = chunk_code_by_lines(
            repo_id="repo-1",
            rel_path="main.py",
            text="def run():\n    return 1\n\nprint(run())\n",
            lines_per_chunk=3,
            overlap=1,
        )

        self.assertEqual("main.py", chunks[0].path)
        self.assertEqual("python", chunks[0].lang)

    def test_code_chunking_prefers_definition_boundaries(self):
        text = (
            "class AuthService:\n"
            "    def login(self):\n"
            "        return 'ok'\n"
            "\n"
            "    def logout(self):\n"
            "        return 'bye'\n"
            "\n"
            "print('done')\n"
        )

        chunks = chunk_code_by_lines(
            repo_id="repo-1",
            rel_path="auth_service.py",
            text=text,
            lines_per_chunk=4,
            overlap=1,
        )

        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(1, chunks[0].start_line)
        self.assertTrue(chunks[0].end_line >= 4)
        self.assertTrue(chunks[1].start_line <= 5)

    def test_extract_text_from_path_supports_txt_and_csv_in_zip(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            txt_path = root / "notes.txt"
            csv_path = root / "table.csv"

            txt_path.write_text("hello zip text", encoding="utf-8")
            csv_path.write_text("id,name\n1,Alice\n", encoding="utf-8")

            self.assertIn("hello zip text", extract_text_from_path(txt_path))
            self.assertIn("name: Alice", extract_text_from_path(csv_path))


if __name__ == "__main__":
    unittest.main()
