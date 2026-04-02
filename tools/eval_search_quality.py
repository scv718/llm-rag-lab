import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.search_services import rerank_search_results


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python3 tools/eval_search_quality.py <eval.json>")
        return 1

    eval_path = Path(sys.argv[1])
    payload = json.loads(eval_path.read_text(encoding="utf-8"))
    total = len(payload.get("cases", []))
    passed = 0

    for case in payload.get("cases", []):
        ranked = rerank_search_results(
            question=case["question"],
            keywords=case.get("keywords", []),
            symbol_hints=case.get("symbol_hints", []),
            merged_hits=case.get("hits", []),
            limit=case.get("limit", 5),
        )

        top_path = extract_top_path(ranked)
        ok = top_path == case.get("expected_top_path")
        if ok:
            passed += 1

        print(
            json.dumps(
                {
                    "name": case.get("name"),
                    "expected_top_path": case.get("expected_top_path"),
                    "actual_top_path": top_path,
                    "pass": ok,
                },
                ensure_ascii=False,
            )
        )

    summary = {
        "total": total,
        "passed": passed,
        "accuracy": round((passed / total), 4) if total else 0.0,
    }
    print(json.dumps({"summary": summary}, ensure_ascii=False))
    return 0 if passed == total else 2


def extract_top_path(ranked_hits: list[dict]) -> str | None:
    if not ranked_hits:
        return None
    top = ranked_hits[0]
    if top["source"] == "keyword":
        return top.get("path")
    return (top.get("metadata") or {}).get("path")


if __name__ == "__main__":
    raise SystemExit(main())
