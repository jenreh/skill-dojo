"""Base of the result models that core operations return."""

from pydantic import BaseModel, ConfigDict


class Result(BaseModel):
    """A JSON-serializable operation result."""

    model_config = ConfigDict(frozen=True, extra="forbid")
