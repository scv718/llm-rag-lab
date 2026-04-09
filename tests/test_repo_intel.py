import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.repo_intel import (
    build_and_store_repo_intel_artifact,
    build_repo_overview_context,
    load_repo_intel_artifact,
    recommended_rerank_limit,
)


class RepoIntelTest(unittest.TestCase):
    def test_build_repo_overview_context_detects_generic_three_stage_flow(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            producer_root = root / "producer"
            relay_root = root / "relay"
            receiver_root = root / "receiver"

            (producer_root / "src/main/java/com/example/producer").mkdir(parents=True, exist_ok=True)
            (relay_root / "src/main/java/com/example/relay").mkdir(parents=True, exist_ok=True)
            (relay_root / "src/main/resources").mkdir(parents=True, exist_ok=True)
            (receiver_root / "src/main/java/com/example/receiver").mkdir(parents=True, exist_ok=True)
            (receiver_root / "src/main/resources").mkdir(parents=True, exist_ok=True)

            (producer_root / "pom.xml").write_text(
                "<project><artifactId>producer-app</artifactId><name>producer-app</name></project>",
                encoding="utf-8",
            )
            (producer_root / "src/main/java/com/example/producer/StreamController.java").write_text(
                "class KamdController { void start(){ new TcpSender(); } }",
                encoding="utf-8",
            )

            (relay_root / "pom.xml").write_text(
                "<project><artifactId>relay-app</artifactId><name>relay-app</name></project>",
                encoding="utf-8",
            )
            (relay_root / "src/main/resources/application-prod.yml").write_text(
                "alerts:\n  alarm-url: http://127.0.0.1:10003/v1/alarmReport\n",
                encoding="utf-8",
            )
            (relay_root / "src/main/java/com/example/relay/InboundReceiver.java").write_text(
                "class KamdReceiver { void run(){ new ServerSocket(27001); } }",
                encoding="utf-8",
            )
            (relay_root / "src/main/java/com/example/relay/OutboundUdpSend.java").write_text(
                "class KamdUdpSend { void run(){ sender.sendData(); } }",
                encoding="utf-8",
            )
            (relay_root / "src/main/java/com/example/relay/RequestController.java").write_text(
                "@RequestMapping(\"/v1/request\") class RequestController {}",
                encoding="utf-8",
            )

            (receiver_root / "pom.xml").write_text(
                "<project><artifactId>control-app</artifactId><name>control-app</name><mainClass>com.example.receiver.Main</mainClass></project>",
                encoding="utf-8",
            )
            (receiver_root / "src/main/resources/application-local.yml").write_text(
                "client:\n  url:\n    upstream: /v1/request\nlistener:\n  stream:\n    port: 20022\n",
                encoding="utf-8",
            )
            (receiver_root / "src/main/java/com/example/receiver/PacketReceiver.java").write_text(
                "class MissReceiver { void run(){ new MulticastSocket(20022); } }",
                encoding="utf-8",
            )
            (receiver_root / "src/main/java/com/example/receiver/AlarmController.java").write_text(
                "@PostMapping(\"/v1/alarmReport\") class AlarmController {}",
                encoding="utf-8",
            )
            (receiver_root / "src/main/java/com/example/receiver/RemoteClientServiceImpl.java").write_text(
                "class RestClientServiceImpl { void call(){ getMedCommonReq(); new RestClient(); } }",
                encoding="utf-8",
            )

            repos = [
                {"repo_id": "producer", "filename": "producer.zip", "extract_path": str(producer_root)},
                {"repo_id": "relay", "filename": "relay.zip", "extract_path": str(relay_root)},
                {"repo_id": "receiver", "filename": "receiver.zip", "extract_path": str(receiver_root)},
            ]

            context, citations = build_repo_overview_context("세 프로젝트 흐름과 연결 설명해줘", repos)

            self.assertIn("[프로젝트 개요]", context)
            self.assertIn("[관계 요약]", context)
            self.assertIn("producer-app -> relay-app", context)
            self.assertIn("relay-app -> control-app", context)
            self.assertTrue(any(item["kind"] == "repo_relation" for item in citations))

    def test_recommended_rerank_limit_expands_for_structure_queries(self):
        self.assertGreater(recommended_rerank_limit("프로젝트 연결 구조 설명", 3, 12), 12)
        self.assertEqual(12, recommended_rerank_limit("특정 메서드 위치 알려줘", 8, 12))

    def test_repo_intel_artifact_can_be_persisted_and_loaded(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src/main/java/com/example").mkdir(parents=True, exist_ok=True)
            (root / "pom.xml").write_text(
                "<project><artifactId>demo-app</artifactId><name>demo-app</name></project>",
                encoding="utf-8",
            )
            (root / "src/main/java/com/example/DemoApplication.java").write_text(
                "public class DemoApplication { public static void main(String[] args) {} }",
                encoding="utf-8",
            )

            repo = {"repo_id": "demo", "filename": "demo.zip", "extract_path": str(root)}
            summary = build_and_store_repo_intel_artifact(repo)
            loaded = load_repo_intel_artifact(repo)

            self.assertIsNotNone(summary)
            self.assertIsNotNone(loaded)
            self.assertEqual(summary["repo_id"], loaded["repo_id"])
            self.assertEqual(summary["display_name"], loaded["display_name"])


if __name__ == "__main__":
    unittest.main()
