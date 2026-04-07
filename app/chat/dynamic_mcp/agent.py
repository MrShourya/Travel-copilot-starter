from app.chat.dynamic_mcp.executor import (
    _build_followup_question,
    execute_planner_tool,
    explain_validation,
    validate_planner_decision,
)
from app.chat.dynamic_mcp.planner import plan_next_action
from app.chat.session_state import TravelSessionState
from app.chat.state_manager import update_state_from_user_query


MAX_DYNAMIC_MCP_STEPS = 5


def _trace_step(step_type: str, title: str, **payload) -> dict:
    return {
        "step_type": step_type,
        "title": title,
        "payload": payload,
    }


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
        "budget_amount",
        "budget_currency",
        "target_currency",
        "flow_stage",
    ]
    return {key: state_dict.get(key) for key in tracked_keys}


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

    state = update_state_from_user_query(state, user_query)

    decision_trace.append(
        _trace_step(
            "state_extraction",
            "Structured values were extracted from the user input",
            extracted_slots=_extract_state_slots(state),
            state_after=state.to_dict(),
            flow_stage_after_parse=state.flow_stage,
        )
    )

    for loop_index in range(1, MAX_DYNAMIC_MCP_STEPS + 1):
        planner_input_snapshot = {
            "user_query": user_query,
            "state": state.to_dict(),
            "prior_tool_results": tool_results,
            "loop_index": loop_index,
        }

        decision_trace.append(
            _trace_step(
                "planner_input",
                f"Planner input for step {loop_index}",
                planner_input=planner_input_snapshot,
            )
        )

        try:
            planner_result = await plan_next_action(
                user_request=user_query,
                session_state=state.to_dict(),
                prior_steps=decision_trace,
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
                    f"Planner failed at step {loop_index}",
                    error=str(exc),
                    fallback_answer=fallback_answer,
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
                f"Planner prompt generated at step {loop_index}",
                prompt_text=planner_result["rendered_prompt"],
            )
        )

        decision_trace.append(
            _trace_step(
                "planner_response",
                f"Planner returned a decision at step {loop_index}",
                raw_response=planner_result["raw_response"],
                parsed_decision=decision.model_dump(),
            )
        )

        decision_trace.append(
            _trace_step(
                "planner_decision",
                f"Planner decision at step {loop_index}",
                decision=decision.model_dump(),
            )
        )

        validation_explanation = explain_validation(decision)

        decision_trace.append(
            _trace_step(
                "input_requirements_check",
                f"Checked whether the selected action has enough inputs at step {loop_index}",
                validation_explanation=validation_explanation,
            )
        )

        validation = validate_planner_decision(decision)

        decision_trace.append(
            _trace_step(
                "validation",
                f"Validation result at step {loop_index}",
                validation=validation,
            )
        )

        if not validation.get("ok"):
            missing_fields = validation.get("missing_fields", [])
            question = validation.get("question") or _build_followup_question(
                missing_fields,
                getattr(decision, "tool_name", None),
            )

            decision_trace.append(
                _trace_step(
                    "validation_failed",
                    f"Validation failed at step {loop_index}",
                    error=validation.get("error"),
                    missing_fields=missing_fields,
                    generated_question=question,
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
                    "ask_user",
                    f"Planner asked user a follow-up question at step {loop_index}",
                    reason=decision.reason,
                    question=decision.question,
                    missing_fields=decision.missing_fields,
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
                    "tool_pre_execution",
                    f"Preparing MCP tool execution at step {loop_index}",
                    tool_name=decision.tool_name,
                    mcp_family=decision.mcp_family,
                    arguments=decision.arguments,
                    argument_provenance=arg_provenance,
                    reason=decision.reason,
                )
            )

            execution = await execute_planner_tool(decision)
            execution_dict = execution.model_dump()

            tool_results.append(execution_dict)

            decision_trace.append(
                _trace_step(
                    "tool_execution",
                    f"MCP tool executed at step {loop_index}",
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
                        f"MCP tool failed at step {loop_index}",
                        fallback_answer=fallback_answer,
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
                    "final_answer",
                    f"Planner returned final answer at step {loop_index}",
                    answer=decision.final_answer,
                    reason=decision.reason,
                )
            )

            return {
                "mode": "dynamic_mcp",
                "response_type": "answer",
                "answer": decision.final_answer,
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

    return {
        "mode": "dynamic_mcp",
        "response_type": "answer",
        "answer": fallback_answer,
        "decision_trace": decision_trace,
        "tool_results": tool_results,
        "state": state.to_dict(),
        "flow_stage": state.flow_stage,
    }