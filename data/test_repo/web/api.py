"""Public API layer."""

from web.handlers import handle_greet


def get_greeting(name: str) -> dict[str, str]:
    return {"message": handle_greet(name)}
