from typing import Protocol

from pydantic import BaseModel, Field


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
        return ModelResponse(
            content="{}",
            model_provider=request.model_provider,
            model_name=request.model_name,
            usage={"prompt_tokens": 0, "completion_tokens": 0},
        )
