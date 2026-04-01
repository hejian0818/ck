"""Service layer."""

from app_core.utils import build_message


class GreetingService:
    """Simple greeting service."""

    def greet(self, name: str) -> str:
        return build_message(name)
