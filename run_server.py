from __future__ import annotations

import argparse
import os


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Run LLM RAG server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--llm-provider", choices=("gemini", "openai", "openai_compatible", "local"))
    parser.add_argument("--llm-model")
    parser.add_argument("--openai-base-url")
    parser.add_argument("--openai-api-key")
    parser.add_argument("--gemini-api-key")
    args = parser.parse_args()

    if args.llm_provider:
        os.environ["LLM_PROVIDER"] = args.llm_provider
    if args.llm_model:
        os.environ["LLM_MODEL"] = args.llm_model
    if args.openai_base_url:
        os.environ["OPENAI_BASE_URL"] = args.openai_base_url
    if args.openai_api_key:
        os.environ["OPENAI_API_KEY"] = args.openai_api_key
    if args.gemini_api_key:
        os.environ["GEMINI_API_KEY"] = args.gemini_api_key

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
