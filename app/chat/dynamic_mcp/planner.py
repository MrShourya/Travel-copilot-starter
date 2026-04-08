import json

from langchain_core.prompts import PromptTemplate
from pydantic import ValidationError

from app.chat.dynamic_mcp.models import PlannerDecision
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

- If approximate or relative information is provided (e.g., "next week"),you MUST derive reasonable defaults and proceed instead of asking the user again.
- Only ask the user if a REQUIRED field is completely missing.
- Consider the values you gathered, dont reconfirm the inputs from the user.
- Do not ask vague questions like "Please provide more details".
- Ask only for the missing fields needed for the next useful step.
- If enough information exists, call exactly one tool.
- For trip planning requests:
  You SHOULD call multiple complementary tools if they add value.

- If budget or cost is mentioned:
  You MUST call estimate_daily_budget_tool after build_trip_summary_tool.

- If a target currency is requested:
  You MUST call convert_currency AFTER budget calculation.

- Do NOT stop after the first useful tool.
- Continue planning until all relevant aspects are covered:
  - itinerary / summary
  - cost estimation
  - currency conversion (if requested)

- Do NOT skip intermediate tools in this sequence.
- Prefer answering once the needed distinct tools have already run.
- Do not call the same tool again if it has already been executed successfully for the same request.
- For itinerary requests, once trip summary information is available, prefer answering instead of calling more tools unless the user explicitly asked for weather or currency conversion.
- You may call multiple different tools across multiple loops if they add value.
- For weather-only requests, once the weather tool has run, answer immediately.
- For currency conversion requests, once the currency tool has run, answer immediately.
- Return valid JSON only.
- Do not include markdown fences.
- If session_state already contains usable values, do not ask the user to repeat or confirm them.
- Relative dates like "next week", "tomorrow", "this weekend", or weekdays should be treated as usable when session_state contains derived start_date/end_date.


## Current user request
{user_request}

## Current session state
{session_state}

## Available tools discovered live from MCP servers
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


_FOLLOWUP_QUESTION_PROMPT = """
You are helping a travel assistant ask the user for missing information.

Generate one short, natural, focused follow-up question.

## Current user request
{user_request}

## Current session state
{session_state}

## Tool the planner wanted to call
{tool_name}

## Missing fields
{missing_fields}

## Tool information
{tool_spec}

Rules:
- Ask only for the missing information.
- Make the question natural and specific.
- Do not mention JSON, validation, schemas, or internal system details.
- Return plain text only.
- If session_state already contains usable values, do not ask the user to repeat or confirm them.
- Relative dates like "next week", "tomorrow", "this weekend", or weekdays should be treated as usable when session_state contains derived start_date/end_date.
- For currency conversion requests, prefer calling the currency tool directly instead of asking for travel fields like city or trip duration.
""".strip()


_FINAL_ANSWER_PROMPT = """
You are the final response generator for a travel assistant.

Write the final user-facing answer using the collected tool results.

## Current user request
{user_request}

## Current session state
{session_state}

## Tool results collected so far
{tool_results}

## Planner reason for answering now
{planner_reason}

## Planner draft answer
{planner_draft_answer}

STRICT INSTRUCTIONS:

Use these instructions only when planning a trip/itenary.
1. If the user is planning a trip:
   - You MUST generate a detailed DAY-WISE itinerary
   - Format:

Day 1:
- Morning:
- Afternoon:
- Evening:

Day 2:
...

2. Do NOT give generic summaries.
3. Do NOT ask follow-up questions if enough data exists.
4. Use real places and realistic suggestions.
5. Consider:
   - city
   - number of days
   - budget
   - weather (if available)

6. Keep it structured and easy to read.

Rules:
- Use the tool results when available.
- Be clear, concise, and directly helpful.
- If the question is not about planning, respond with only the answer based on the inputs.
- Do not mention internal planner loops, validation, or MCP internals.
- If tool results are incomplete, answer honestly and avoid inventing facts.
- Return plain text only.
- If session_state already contains usable values, do not ask the user to repeat or confirm them.
- Relative dates like "next week", "tomorrow", "this weekend", or weekdays should be treated as usable when session_state contains derived start_date/end_date.
- For currency conversion requests, prefer calling the currency tool directly instead of asking for travel fields like city or trip duration.
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
    available_tools: list[dict],
    provider: str,
    temperature: float = 0.0,
) -> dict:
    llm = get_chat_model(provider=provider, temperature=temperature)

    prompt = PromptTemplate.from_template(_DYNAMIC_MCP_PLANNER_PROMPT)

    prompt_inputs = {
        "user_request": user_request,
        "session_state": json.dumps(session_state, ensure_ascii=False, indent=2),
        "available_tools": json.dumps(available_tools, ensure_ascii=False, indent=2),
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


async def generate_followup_question(
    *,
    user_request: str,
    session_state: dict,
    tool_name: str | None,
    missing_fields: list[str],
    tool_spec: dict | None,
    provider: str,
) -> dict:
    llm = get_chat_model(provider=provider, temperature=0.0)
    prompt = PromptTemplate.from_template(_FOLLOWUP_QUESTION_PROMPT)
    chain = prompt | llm

    prompt_inputs = {
        "user_request": user_request,
        "session_state": json.dumps(session_state, ensure_ascii=False, indent=2),
        "tool_name": tool_name or "",
        "missing_fields": json.dumps(missing_fields, ensure_ascii=False),
        "tool_spec": json.dumps(tool_spec or {}, ensure_ascii=False, indent=2),
    }

    rendered_prompt = prompt.format(**prompt_inputs)
    response = await chain.ainvoke(prompt_inputs)

    raw_text = response.content if hasattr(response, "content") else str(response)

    return {
        "question": raw_text.strip(),
        "raw_response": raw_text,
        "rendered_prompt": rendered_prompt,
    }


async def generate_final_answer(
    *,
    user_request: str,
    session_state: dict,
    tool_results: list[dict],
    planner_reason: str,
    planner_draft_answer: str | None,
    provider: str,
) -> dict:
    llm = get_chat_model(provider=provider, temperature=0.2)
    prompt = PromptTemplate.from_template(_FINAL_ANSWER_PROMPT)
    chain = prompt | llm

    prompt_inputs = {
        "user_request": user_request,
        "session_state": json.dumps(session_state, ensure_ascii=False, indent=2),
        "tool_results": json.dumps(tool_results, ensure_ascii=False, indent=2),
        "planner_reason": planner_reason,
        "planner_draft_answer": planner_draft_answer or "",
    }

    rendered_prompt = prompt.format(**prompt_inputs)
    response = await chain.ainvoke(prompt_inputs)

    raw_text = response.content if hasattr(response, "content") else str(response)

    return {
        "final_answer": raw_text.strip(),
        "raw_response": raw_text,
        "rendered_prompt": rendered_prompt,
    }