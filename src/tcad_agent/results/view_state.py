"""Serializable, reversible state for a canonical scientific view."""

from typing import Literal, Self

from pydantic import Field, model_validator

from tcad_agent.domain.models import StrictModel


class ResultViewState(StrictModel):
    dataset_id: str = Field(min_length=1, max_length=160)
    scale: Literal["linear", "log", "signed_log"] = "linear"
    complex_component: Literal["magnitude", "phase", "real", "imaginary"] = "magnitude"
    slice_indices: dict[str, int] = Field(default_factory=dict)
    viewport_minimum: float | None = None
    viewport_maximum: float | None = None

    @model_validator(mode="after")
    def validate_viewport(self) -> Self:
        if (self.viewport_minimum is None) != (self.viewport_maximum is None):
            raise ValueError("viewport bounds must be supplied together")
        if (
            self.viewport_minimum is not None
            and self.viewport_maximum is not None
            and self.viewport_minimum >= self.viewport_maximum
        ):
            raise ValueError("viewport minimum must be less than maximum")
        if any(index < 0 for index in self.slice_indices.values()):
            raise ValueError("slice indices cannot be negative")
        return self
