"""Rule configuration for summary generation."""

from __future__ import annotations

MODULE_RESPONSIBILITY_RULES: tuple[tuple[str, str], ...] = (
    ("api", "API Layer"),
    ("controller", "API Layer"),
    ("service", "Business Logic"),
    ("business", "Business Logic"),
    ("model", "Data Model"),
    ("entity", "Data Model"),
    ("util", "Utility"),
    ("helper", "Utility"),
)
MODULE_RESPONSIBILITY_DEFAULT = "Module"
MODULE_CORE_FILE_LIMIT = 5
MODULE_CORE_SYMBOL_LIMIT = 10

FILE_RESPONSIBILITY_RULES: tuple[tuple[str, str], ...] = (
    ("test", "Test"),
    ("config", "Configuration"),
    ("main", "Entry Point"),
    ("app", "Entry Point"),
)
FILE_LANGUAGE_DEFAULTS: dict[str, str] = {
    "python": "Python Module",
    "java": "Java Class",
    "javascript": "JavaScript Module",
    "typescript": "TypeScript Module",
    "go": "Go Package",
    "rust": "Rust Module",
    "cpp": "C++ Source File",
    "c": "C Source File",
}
FILE_RESPONSIBILITY_DEFAULT = "Source File"

SYMBOL_RESPONSIBILITY_RULES: tuple[tuple[str, str], ...] = (
    ("get", "Query"),
    ("find", "Query"),
    ("query", "Query"),
    ("create", "Create"),
    ("add", "Create"),
    ("insert", "Create"),
    ("update", "Update"),
    ("modify", "Update"),
    ("delete", "Delete"),
    ("remove", "Delete"),
    ("validate", "Validation"),
    ("check", "Validation"),
)

RELATION_LABEL_TEMPLATES: dict[str, str] = {
    "calls": "{source} calls {target}",
    "extends": "{source} extends {target}",
    "implements": "{source} implements {target}",
    "depends_on": "{source} depends on {target}",
    "references": "{source} references {target}",
}
