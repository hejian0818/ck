"""Run a local demo server with an interactive QA prompt."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from urllib import request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn


def run_server() -> None:
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_level="info")


def main() -> None:
    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    time.sleep(2)
    print("CodeWiki demo server is running at http://127.0.0.1:8000")
    print("Use Ctrl+C to exit.")
    while True:
        try:
            question = input("Question> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            continue
        if question.lower() in {"quit", "exit"}:
            break
        try:
            response = request.urlopen("http://127.0.0.1:8000/health", timeout=5)
            print(f"Server status: {response.status}")
            print("Submit QA requests with POST /qa/ask after building an index.")
        except Exception as exc:
            print(f"Server request failed: {exc}")


if __name__ == "__main__":
    main()
