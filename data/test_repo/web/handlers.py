"""Request handlers."""

from app_core.services import GreetingService


def handle_greet(name: str) -> str:
    service = GreetingService()
    return service.greet(name)
