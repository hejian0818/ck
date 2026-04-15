"""CLI to build and persist a repository index."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api.dependencies import get_graph_repository
from app.core.config import settings
from app.core.logging import configure_logging
from app.services.cleanarch.graph_builder import GraphBuilder
from app.services.indexing.embedding_builder import EmbeddingBuilder
from app.storage.vector_store import VectorStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build CodeWiki repository index")
    parser.add_argument("--repo-path", required=True, help="Path to repository")
    parser.add_argument("--branch", default="main", help="Repository branch")
    parser.add_argument("--no-incremental", action="store_true", help="Disable incremental reuse of unchanged files")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging()
    repository = get_graph_repository()
    repository.initialize_schema()
    graph_builder = GraphBuilder()
    if repository.engine.dialect.name == "postgresql":
        repository.init_vector_tables()
        graph_builder = GraphBuilder(
            embedding_builder=EmbeddingBuilder(),
            vector_store=VectorStore(settings.DATABASE_URL),
        )

    previous_graph = None
    if not args.no_incremental:
        previous_repo_id = repository.find_repo_id_by_path(str(Path(args.repo_path).resolve()))
        if previous_repo_id is not None:
            previous_graph = repository.load_graphcode(previous_repo_id)

    graph = graph_builder.build_graph(
        repo_path=args.repo_path,
        branch=args.branch,
        previous_graph=previous_graph,
    )
    repository.save_graphcode(graph)
    print(f"repo_id={graph.repo_meta.repo_id}")
    print(f"modules={len(graph.modules)} files={len(graph.files)} symbols={len(graph.symbols)} relations={len(graph.relations)}")
    print(
        "incremental="
        f"{graph_builder.last_build_stats['incremental']} parsed={graph_builder.last_build_stats['parsed_files']} "
        f"reused={graph_builder.last_build_stats['reused_files']} deleted={graph_builder.last_build_stats['deleted_files']}"
    )


if __name__ == "__main__":
    main()
