import json

from langchain_core.prompts import PromptTemplate
from pydantic import ValidationError

from app.chat.dynamic_mcp.models import PlannerDecision
from app.chat.dynamic_mcp.registry import list_tools_for_prompt
from app.chat.model_factory import get_chat_model


_DYNAMIC_MCP_PLANNER_PROMPT = """
You are a travel-planning tool-routing planner.

Your job is to decide the NEXT best action in a travel assistant workflow.

You must choose exactly one action:
1. ask_user
2. call_tool
3. answer

You are NOT the final assistant unless action="answer".
You are a controller that decides what happens next.

## Rules

- If required information for a useful tool is missing, ask the user a focused question.
- Do not ask vague questions like "Please provide more details".
- Ask only for the missing fields needed for the next useful step.
- If enough information exists, call exactly one tool.
- Do not call multiple tools in one decision.
- Prefer checking readiness before summary if the trip request is still incomplete.
- If the user explicitly asks for weather but date/range is missing, ask when.
- If the user asks for itinerary creation but city or days are missing, ask for them.
- If you already have enough information and tool calls are not needed, answer directly.
- Return valid JSON only.
- Do not include markdown fences.

## Current user request
{user_request}

## Current session state
{session_state}

## Available tools
{available_tools}

## Previous steps in this turn
{prior_steps}

## Output schema

Return JSON with this structure:
{{
  "action": "ask_user" | "call_tool" | "answer",
  "reason": "why this is the best next step",

  "question": "required only for ask_user",
  "missing_fields": ["field1", "field2"],

  "tool_name": "required only for call_tool",
  "mcp_family": "required only for call_tool",
  "arguments": {{}},

  "final_answer": "required only for answer"
}}
""".strip()


def _extract_json(text: str) -> dict:
    text = text.strip()

    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()

    return json.loads(text)


async def plan_next_action(
    *,
    user_request: str,
    session_state: dict,
    prior_steps: list[dict],
    provider: str,
    temperature: float = 0.0,
) -> dict:
    llm = get_chat_model(provider=provider, temperature=temperature)

    prompt = PromptTemplate.from_template(_DYNAMIC_MCP_PLANNER_PROMPT)

    prompt_inputs = {
        "user_request": user_request,
        "session_state": json.dumps(session_state, ensure_ascii=False, indent=2),
        "available_tools": json.dumps(
            list_tools_for_prompt(), ensure_ascii=False, indent=2
        ),
        "prior_steps": json.dumps(prior_steps, ensure_ascii=False, indent=2),
    }

    rendered_prompt = prompt.format(**prompt_inputs)

    chain = prompt | llm
    response = await chain.ainvoke(prompt_inputs)

    raw_text = response.content if hasattr(response, "content") else str(response)

    try:
        parsed = _extract_json(raw_text)
    except Exception as exc:
        raise ValueError(
            f"Planner returned non-JSON output: {raw_text}"
        ) from exc

    try:
        decision = PlannerDecision.model_validate(parsed)
    except ValidationError as exc:
        raise ValueError(
            f"Planner JSON did not match schema: {parsed}"
        ) from exc

    return {
        "decision": decision,
        "raw_response": raw_text,
        "rendered_prompt": rendered_prompt,
    }