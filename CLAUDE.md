# CodeWiki Project Instructions

## Project Overview
单代码仓设计文档生成与代码问答系统。支持自动生成设计文档和交互式代码问答。

## Tech Stack Decisions

### Backend
- Language: Python 3.11+
- Framework: FastAPI
- Data Validation: Pydantic v2
- Server: Uvicorn

### Storage
- Metadata DB: PostgreSQL
- Vector Store: pgvector (PostgreSQL extension)
- File Storage: Local filesystem

### Code Parsing (Multi-language)
- Java: Spoon
- C/C++: Eclipse CDT
- Python/JavaScript/Go/Rust/etc: Tree-sitter
- Architecture: Adapter pattern for unified output

### Package Management
- Tool: uv
- Python Version: 3.11+

### LLM Integration
- API: OpenAI-compatible interface
- Supports: Ollama, vLLM, domestic models, etc.

## Development Phases

### Phase 1: Foundation (Current)
- cleanarch module with multi-language parser adapters
- graphcode.json schema and generation
- 4-layer indexing (module/file/symbol/relation)
- Graph index for relationships
- Span location mapping
- Basic QA API with explicit anchor
- Anchor Memory
- Context Builder (basic version)

### Phase 2: Enhancement
- Rule-based summary generation
- Vector indexing with pgvector
- Name-based anchor matching
- Anchor inheritance
- Retrieval ranking
- Memory management (retrieval/focus)
- Metrics calculation (A/C/E/G/R)
- State machine for strategy switching
- Degradation handling

### Phase 3: Document Generation
- Document skeleton planning
- Section-level retrieval
- Section generation
- PlantUML diagram generation
- Document-diagram consistency review
- Task Memory

### Phase 4: Production Ready
- Advanced degradation modes
- Comprehensive logging and metrics
- Caching optimization
- Configuration management
- Demo, README, and tests

## Code Style

### Naming
- Files: snake_case.py
- Classes: PascalCase
- Functions/variables: snake_case
- Constants: UPPER_SNAKE_CASE

### Imports
```python
# Standard library
import os
from typing import Optional

# Third-party
from fastapi import FastAPI
from pydantic import BaseModel

# Local
from app.core.config import settings
from app.models.graph_objects import Module
```

### Logging
- Use structured JSON logging
- Log all critical decision points (anchor resolution, retrieval, state transitions)
- Include metrics in logs (A/C/E/G/R values)

### Configuration
- All thresholds in config files (no hardcoded magic numbers)
- Use environment variables for secrets
- Provide sensible defaults

### Type Hints
- All functions must have type hints
- Use Pydantic models for data structures
- Use TypedDict or dataclass for internal structures

## Project Structure
```
ck/
  app/
    api/          # FastAPI endpoints
    core/         # Config, logging, constants, thresholds
    models/       # Pydantic models and data structures
    services/     # Business logic
      cleanarch/  # Multi-language parsing
      indexing/   # Index building
      retrieval/  # Search and retrieval
      agents/     # Document and QA agents
      context/    # Context building
      memory/     # Memory management
      review/     # Validation
      diagrams/   # PlantUML generation
    storage/      # DB and vector store access
    tests/        # Unit tests
  scripts/        # CLI tools
  data/           # Data storage
  README.md
  CLAUDE.md
  pyproject.toml  # uv project config
```

## Development Principles
1. Build skeleton first, add strategies later
2. Main path first, enhancement paths later
3. Runnable first, optimization later
4. All switching conditions must be explicit code logic
5. All core objects must have stable IDs
6. Logs, configs, thresholds must be observable and tunable
7. Thresholds in config files, not scattered in code
8. All APIs and data structures use type definitions

## Git Workflow
- Commit after each meaningful step
- Push to GitHub after each commit
- Commit message format: "feat/fix/refactor: brief description"
- Never commit secrets or credentials

## Current Status
- Phase: All phases complete (Phase 1-4)
- Tests: 94 passing
- All features implemented and tested
