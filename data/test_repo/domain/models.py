"""Domain models."""


class User:
    """Simple user model."""

    def __init__(self, name: str) -> None:
        self.name = name

    def display_name(self) -> str:
        return self.name.title()
