"""Safe, structured failures from prompt preparation."""

from __future__ import annotations

from collections.abc import Sequence


class ModelResponseError(RuntimeError):
    """Safe error for unavailable or invalid preparation model output."""


class ResearcherInputRequiredError(ModelResponseError):
    """A model tried to source researcher-owned intent from another authority."""

    def __init__(self, field_paths: Sequence[str], detail: str) -> None:
        self.field_paths = tuple(dict.fromkeys(field_paths))
        self.detail = detail
        joined = ", ".join(self.field_paths)
        super().__init__(
            f"Researcher confirmation is required for researcher-owned field: {joined}."
        )
