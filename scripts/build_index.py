"""CLI to build and persist a repository index."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api.dependencies import get_graph_repository
from app.core.logging import configure_logging
from app.services.cleanarch.graph_builder import GraphBuilder


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build CodeWiki repository index")
    parser.add_argument("--repo-path", required=True, help="Path to repository")
    parser.add_argument("--branch", default="main", help="Repository branch")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging()
    graph = GraphBuilder().build_graph(repo_path=args.repo_path, branch=args.branch)
    repository = get_graph_repository()
    repository.initialize_schema()
    repository.save_graphcode(graph)
    print(f"repo_id={graph.repo_meta.repo_id}")
    print(f"modules={len(graph.modules)} files={len(graph.files)} symbols={len(graph.symbols)} relations={len(graph.relations)}")


if __name__ == "__main__":
    main()
