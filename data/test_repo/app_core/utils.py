"""Utility helpers."""


def normalize_name(name: str) -> str:
    return name.strip().lower()


def build_message(name: str) -> str:
    return f"hello, {normalize_name(name)}"
