from pydantic import BaseModel, Field


class Reason(BaseModel):
    step_key: str
    summary: str


class Act(BaseModel):
    step_key: str
    tool_name: str | None = None
    tool_input: dict = Field(default_factory=dict)


class Observe(BaseModel):
    step_key: str
    status: str
    output: dict = Field(default_factory=dict)


class ReActTrace(BaseModel):
    reason: Reason
    act: Act
    observe: Observe
