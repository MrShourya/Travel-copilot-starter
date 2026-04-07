from typing import Any, Literal

from pydantic import BaseModel, Field


PlannerAction = Literal["ask_user", "call_tool", "answer"]


class PlannerDecision(BaseModel):
    action: PlannerAction
    reason: str

    question: str | None = None
    missing_fields: list[str] = Field(default_factory=list)

    tool_name: str | None = None
    mcp_family: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)

    final_answer: str | None = None


class ExecutionResult(BaseModel):
    ok: bool
    tool_name: str | None = None
    mcp_family: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    missing_fields: list[str] = Field(default_factory=list)


class PlannerStepTrace(BaseModel):
    step_type: str
    title: str
    payload: dict[str, Any] = Field(default_factory=dict)