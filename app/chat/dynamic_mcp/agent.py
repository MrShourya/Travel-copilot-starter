from app.chat.dynamic_mcp.executor import (
    _build_followup_question,
    execute_planner_tool,
    explain_validation,
    validate_planner_decision,
)
from app.chat.dynamic_mcp.planner import (
    generate_final_answer,
    generate_followup_question,
    plan_next_action,
)
from app.chat.dynamic_mcp.tool_catalog import discover_live_tool_catalog, get_tool_spec
from app.chat.session_state import TravelSessionState
from app.chat.state_manager import update_state_from_user_query


MAX_DYNAMIC_MCP_STEPS = 5


def _trace_step(
    step_type: str,
    title: str,
    *,
    loop_index: int | None = None,
    **payload,
) -> dict:
    return {
        "step_type": step_type,
        "title": title,
        "loop_index": loop_index,
        "payload": payload,
    }

from datetime import datetime, timedelta


def _derive_date_slots(state_dict: dict) -> dict:
    date_text = state_dict.get("date_text")
    trip_days = state_dict.get("trip_days")

    derived = {
        "start_date": state_dict.get("start_date"),
        "end_date": state_dict.get("end_date"),
    }

    if not date_text:
        return derived

    try:
        start_dt = datetime.strptime(date_text.strip(), "%Y-%m-%d").date()
        derived["start_date"] = start_dt.isoformat()

        if trip_days and isinstance(trip_days, int) and trip_days > 0:
            end_dt = start_dt + timedelta(days=trip_days - 1)
            derived["end_date"] = end_dt.isoformat()
    except Exception:
        pass

    return derived

def _extract_arg_provenance(
    arguments: dict,
    state_dict: dict,
    raw_user_query: str,
) -> dict:
    provenance = {}

    state_keys = set(state_dict.keys())
    lowered_query = raw_user_query.lower()

    for key, value in arguments.items():
        source = "unknown"

        if key in state_keys and state_dict.get(key) == value:
            source = "session_state"
        elif isinstance(value, str) and value.lower() in lowered_query:
            source = "user_query"
        elif key in {"travel_style"}:
            source = "default"
        elif key in {"currency"} and state_dict.get("target_currency") == value:
            source = "target_currency"
        elif key in {"currency"} and state_dict.get("budget_currency") == value:
            source = "budget_currency"

        provenance[key] = {
            "value": value,
            "source": source,
        }

    return provenance


def _summarize_user_input(user_query: str) -> dict:
    lowered = user_query.lower()

    keywords = {
        "itinerary": "itinerary" in lowered,
        "weather": "weather" in lowered or "forecast" in lowered,
        "budget": "budget" in lowered,
        "currency": "convert" in lowered or "currency" in lowered,
        "packing": "packing" in lowered,
    }

    return {
        "raw_text": user_query,
        "normalized_text": lowered.strip(),
        "keyword_hints": keywords,
    }


def _extract_state_slots(state: TravelSessionState) -> dict:
    state_dict = state.to_dict()
    tracked_keys = [
        "city",
        "trip_days",
        "date_text",
        "start_date",
        "end_date",
        "budget_amount",
        "budget_currency",
        "target_currency",
        "flow_stage",
    ]
    return {key: state_dict.get(key) for key in tracked_keys}

def _compact_trace(decision_trace):
    """
    Keep only minimal reasoning context for LLM.
    """
    compact = []

    for step in decision_trace:
        step_type = step.get("step_type")

        # only keep essential reasoning
        if step_type in [
            "planner_response",
            "action_decision",
            "tool_execution",
        ]:
            compact.append({
                "step_type": step_type,
                "summary": str(step.get("payload"))[:300]  # truncate
            })

    return compact[-5:]  # only last 5 steps

def _compact_tool_results(results):
    compact = []
    for r in results:
        compact.append({
            "tool": r.get("tool_name"),
            "summary": str(r.get("data"))[:300]
        })
    return compact[-3:]

def _compact_tools(tools):
    return [
        {
            "tool_name": t.get("tool_name"),
            "description": t.get("description"),
            "args": t.get("args", [])[:5],  # limit args
        }
        for t in tools
    ]

def _compact_state(state):
    s = state.to_dict()
    return {
        "city": s.get("city"),
        "trip_days": s.get("trip_days"),
        "start_date": s.get("start_date"),
        "end_date": s.get("end_date"),
        "budget_amount": s.get("budget_amount"),
        "budget_currency": s.get("budget_currency"),
    }

async def answer_user_dynamic(
    *,
    user_query: str,
    provider: str,
    state: TravelSessionState,
    temperature: float = 0.0,
) -> dict:
    decision_trace: list[dict] = []
    tool_results: list[dict] = []

    decision_trace.append(
        _trace_step(
            "turn_start",
            "Dynamic MCP turn started",
            user_query=user_query,
            provider=provider,
            flow_stage_before=state.flow_stage,
            state_before=state.to_dict(),
        )
    )

    decision_trace.append(
        _trace_step(
            "input_understanding",
            "Input text was analyzed for intent hints",
            input_analysis=_summarize_user_input(user_query),
        )
    )

    # IMPORTANT: update the live state first
    state = update_state_from_user_query(state, user_query)
    derived_dates = _derive_date_slots(state.to_dict())
    if derived_dates.get("start_date"):
        state.start_date = derived_dates["start_date"]
    if derived_dates.get("end_date"):
        state.end_date = derived_dates["end_date"]
    decision_trace.append(
        _trace_step(
            "state_extraction",
            "Structured values were extracted from the user input",
            extracted_slots=_extract_state_slots(state),
            state_after=state.to_dict(),
            flow_stage_after_parse=state.flow_stage,
        )
    )

    available_tools = await discover_live_tool_catalog()

    decision_trace.append(
        _trace_step(
            "live_tool_catalog",
            "Live tool catalog was discovered from MCP servers",
            available_tools=_compact_tools(available_tools)
        )
    )

    for loop_index in range(1, MAX_DYNAMIC_MCP_STEPS + 1):
        planner_input_snapshot = {
            "user_query": user_query,
            "state": state.to_dict(),
            "prior_tool_results": tool_results,
            "loop_index": loop_index,
            "available_tool_names": [t.get("tool_name") for t in available_tools],
        }

        decision_trace.append(
            _trace_step(
                "planner_input",
                f"Planner input for loop {loop_index}",
                loop_index=loop_index,
                planner_input=planner_input_snapshot,
            )
        )

        try:
            planner_result = await plan_next_action(
                user_request=user_query,
                session_state=_compact_state(state),
                prior_steps=_compact_trace(decision_trace),
                available_tools=available_tools,
                provider=provider,
                temperature=temperature,
            )
            decision = planner_result["decision"]
        except Exception as exc:
            fallback_answer = (
                "I hit an issue while planning the next MCP step. "
                "Please try again with a bit more detail."
            )

            decision_trace.append(
                _trace_step(
                    "planner_error",
                    f"Planner failed at loop {loop_index}",
                    loop_index=loop_index,
                    error=str(exc),
                    fallback_answer=fallback_answer,
                )
            )

            decision_trace.append(
                _trace_step(
                    "final_output",
                    "Workflow ended with planner error",
                    answer=fallback_answer,
                    response_type="answer",
                )
            )

            return {
                "mode": "dynamic_mcp",
                "response_type": "answer",
                "answer": fallback_answer,
                "decision_trace": decision_trace,
                "tool_results": tool_results,
                "state": state.to_dict(),
                "flow_stage": state.flow_stage,
            }

        decision_trace.append(
            _trace_step(
                "planner_prompt",
                f"Planner prompt generated at loop {loop_index}",
                loop_index=loop_index,
                prompt_text=planner_result["rendered_prompt"],
            )
        )

        decision_trace.append(
            _trace_step(
                "planner_response",
                f"Planner returned a decision at loop {loop_index}",
                loop_index=loop_index,
                raw_response=planner_result["raw_response"],
                parsed_decision=decision.model_dump(),
            )
        )

        # IMPORTANT: enrich tool arguments from current state before validation
        if decision.action == "call_tool":
            enriched_args = dict(decision.arguments or {})
            state_dict = state.to_dict()

            for key in [
                "city",
                "trip_days",
                "start_date",
                "end_date",
                "date_text",
                "budget_amount",
                "budget_currency",
                "target_currency",
            ]:
                if key not in enriched_args and state_dict.get(key) is not None:
                    enriched_args[key] = state_dict[key]

            decision.arguments = enriched_args

            decision_trace.append(
                _trace_step(
                    "argument_enrichment",
                    f"Planner arguments were enriched from state at loop {loop_index}",
                    loop_index=loop_index,
                    enriched_arguments=enriched_args,
                )
            )

        validation_explanation = explain_validation(decision, available_tools)

        decision_trace.append(
            _trace_step(
                "input_requirements_check",
                f"Checked whether the selected action has enough inputs at loop {loop_index}",
                loop_index=loop_index,
                validation_explanation=validation_explanation,
            )
        )

        validation = validate_planner_decision(
                        decision,
                        available_tools,
                        state_context=state.to_dict()
                    )

        decision_trace.append(
            _trace_step(
                "validation_result",
                f"Validation result at loop {loop_index}",
                loop_index=loop_index,
                validation=validation,
            )
        )

        if not validation.get("ok"):
            missing_fields = validation.get("missing_fields", [])
            tool_spec = get_tool_spec(
                available_tools,
                getattr(decision, "tool_name", "") or "",
            )

            try:
                followup_result = await generate_followup_question(
                    user_request=user_query,
                    session_state=state.to_dict(),
                    tool_name=getattr(decision, "tool_name", None),
                    missing_fields=missing_fields,
                    tool_spec=tool_spec,
                    provider=provider,
                )
                question = followup_result["question"]

                decision_trace.append(
                    _trace_step(
                        "missing_field_prompt",
                        f"Prompt built to generate missing-field question at loop {loop_index}",
                        loop_index=loop_index,
                        prompt_text=followup_result["rendered_prompt"],
                    )
                )

                decision_trace.append(
                    _trace_step(
                        "missing_field_response",
                        f"LLM generated missing-field question at loop {loop_index}",
                        loop_index=loop_index,
                        raw_response=followup_result["raw_response"],
                        question=question,
                    )
                )

            except Exception:
                question = _build_followup_question(
                    missing_fields,
                    getattr(decision, "tool_name", None),
                )

            decision_trace.append(
                _trace_step(
                    "action_decision",
                    f"Action decision at loop {loop_index}",
                    loop_index=loop_index,
                    action="ask_user",
                    reason=validation.get("error"),
                    question=question,
                    missing_fields=missing_fields,
                )
            )

            decision_trace.append(
                _trace_step(
                    "final_output",
                    "Workflow ended by asking the user for missing inputs",
                    answer=question,
                    response_type="question",
                )
            )

            return {
                "mode": "dynamic_mcp",
                "response_type": "question",
                "answer": question,
                "decision_trace": decision_trace,
                "tool_results": tool_results,
                "state": state.to_dict(),
                "flow_stage": state.flow_stage,
            }

        if decision.action == "ask_user":
            decision_trace.append(
                _trace_step(
                    "action_decision",
                    f"Action decision at loop {loop_index}",
                    loop_index=loop_index,
                    action="ask_user",
                    reason=decision.reason,
                    question=decision.question,
                    missing_fields=decision.missing_fields,
                )
            )

            decision_trace.append(
                _trace_step(
                    "final_output",
                    "Workflow ended by asking the user a follow-up question",
                    answer=decision.question,
                    response_type="question",
                )
            )

            return {
                "mode": "dynamic_mcp",
                "response_type": "question",
                "answer": decision.question,
                "decision_trace": decision_trace,
                "tool_results": tool_results,
                "state": state.to_dict(),
                "flow_stage": state.flow_stage,
            }

        if decision.action == "call_tool":
            arg_provenance = _extract_arg_provenance(
                decision.arguments,
                state.to_dict(),
                user_query,
            )

            decision_trace.append(
                _trace_step(
                    "action_decision",
                    f"Action decision at loop {loop_index}",
                    loop_index=loop_index,
                    action="call_tool",
                    reason=decision.reason,
                    tool_name=decision.tool_name,
                    mcp_family=decision.mcp_family,
                    arguments=decision.arguments,
                    argument_provenance=arg_provenance,
                )
            )

            execution = await execute_planner_tool(decision)
            execution_dict = execution.model_dump()

            tool_results.append(execution_dict)

            decision_trace.append(
                _trace_step(
                    "tool_execution",
                    f"MCP tool executed at loop {loop_index}",
                    loop_index=loop_index,
                    tool_name=decision.tool_name,
                    mcp_family=decision.mcp_family,
                    execution=execution_dict,
                )
            )

            if not execution.ok:
                fallback_answer = (
                    f"I tried to call {decision.tool_name}, but it failed. "
                    f"Error: {execution.error}"
                )

                decision_trace.append(
                    _trace_step(
                        "tool_execution_failed",
                        f"MCP tool failed at loop {loop_index}",
                        loop_index=loop_index,
                        tool_name=decision.tool_name,
                        fallback_answer=fallback_answer,
                    )
                )

                decision_trace.append(
                    _trace_step(
                        "final_output",
                        "Workflow ended because tool execution failed",
                        answer=fallback_answer,
                        response_type="answer",
                    )
                )

                return {
                    "mode": "dynamic_mcp",
                    "response_type": "answer",
                    "answer": fallback_answer,
                    "decision_trace": decision_trace,
                    "tool_results": tool_results,
                    "state": state.to_dict(),
                    "flow_stage": state.flow_stage,
                }

            continue

        if decision.action == "answer":
            decision_trace.append(
                _trace_step(
                    "action_decision",
                    f"Action decision at loop {loop_index}",
                    loop_index=loop_index,
                    action="answer",
                    reason=decision.reason,
                    planner_draft_answer=decision.final_answer,
                )
            )

            try:
                final_answer_result = await generate_final_answer(
                    user_request=user_query,
                    session_state=state.to_dict(),
                    tool_results=_compact_tool_results(tool_results),
                    planner_reason=decision.reason,
                    planner_draft_answer=decision.final_answer,
                    provider=provider,
                )

                decision_trace.append(
                    _trace_step(
                        "final_answer_prompt",
                        "Prompt built to generate the final answer",
                        prompt_text=final_answer_result["rendered_prompt"],
                    )
                )

                decision_trace.append(
                    _trace_step(
                        "final_answer_response",
                        "LLM generated the final user-facing answer",
                        raw_response=final_answer_result["raw_response"],
                        answer=final_answer_result["final_answer"],
                    )
                )

                final_answer_text = final_answer_result["final_answer"]

            except Exception:
                final_answer_text = (
                    decision.final_answer or "I have enough information to answer now."
                )

            decision_trace.append(
                _trace_step(
                    "final_output",
                    "Workflow ended with a final answer",
                    answer=final_answer_text,
                    response_type="answer",
                )
            )

            return {
                "mode": "dynamic_mcp",
                "response_type": "answer",
                "answer": final_answer_text,
                "decision_trace": decision_trace,
                "tool_results": tool_results,
                "state": state.to_dict(),
                "flow_stage": state.flow_stage,
            }

    fallback_answer = (
        "I reached the maximum planning steps for this turn. "
        "Please reply with a bit more detail so I can continue."
    )

    decision_trace.append(
        _trace_step(
            "loop_limit",
            "Maximum dynamic MCP planning steps reached",
            max_steps=MAX_DYNAMIC_MCP_STEPS,
            fallback_answer=fallback_answer,
        )
    )

    decision_trace.append(
        _trace_step(
            "final_output",
            "Workflow ended because loop limit was reached",
            answer=fallback_answer,
            response_type="answer",
        )
    )

    return {
        "mode": "dynamic_mcp",
        "response_type": "answer",
        "answer": fallback_answer,
        "decision_trace": decision_trace,
        "tool_results": tool_results,
        "state": state.to_dict(),
        "flow_stage": state.flow_stage,
    }