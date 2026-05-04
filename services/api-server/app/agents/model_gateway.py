from typing import Protocol

from pydantic import BaseModel, Field

from app.observability.metrics import (
    model_calls_total,
    model_tokens_input_total,
    model_tokens_output_total,
)


class ModelMessage(BaseModel):
    role: str
    content: str


class ModelRequest(BaseModel):
    model_provider: str
    model_name: str
    messages: list[ModelMessage]
    response_format: str = "json"


class ModelResponse(BaseModel):
    content: str
    model_provider: str
    model_name: str
    usage: dict = Field(default_factory=dict)


class ModelGateway(Protocol):
    def complete(self, request: ModelRequest) -> ModelResponse:
        """Call an OpenAI-compatible gateway through the platform boundary."""


class MockModelGateway:
    def complete(self, request: ModelRequest) -> ModelResponse:
        model_calls_total.inc()
        model_tokens_input_total.inc(0)
        model_tokens_output_total.inc(0)
        return ModelResponse(
            content="{}",
            model_provider=request.model_provider,
            model_name=request.model_name,
            usage={"prompt_tokens": 0, "completion_tokens": 0},
        )
