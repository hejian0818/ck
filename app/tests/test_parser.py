"""Parser tests."""

from __future__ import annotations

import unittest
from pathlib import Path

from app.services.cleanarch.treesitter_adapter import TreeSitterAdapter


class TreeSitterAdapterTests(unittest.TestCase):
    def test_parse_python_file_extracts_symbols_and_calls(self) -> None:
        path = Path("data/test_repo/app_core/services.py")
        result = TreeSitterAdapter().parse_file(str(path))
        names = [symbol.qualified_name for symbol in result.symbols]
        calls = [(relation.source_id, relation.target_id) for relation in result.relations]
        self.assertIn("GreetingService", names)
        self.assertIn("GreetingService.greet", names)
        self.assertIn(("GreetingService.greet", "build_message"), calls)


if __name__ == "__main__":
    unittest.main()
