from langchain_core.prompts import PromptTemplate
from langfuse.langchain import CallbackHandler

from app.chat.model_factory import get_chat_model
from app.chat.prompt_loader import get_system_prompt
from app.chat.session_state import TravelSessionState
from app.chat.state_manager import update_state_from_user_query
from app.chat.tool_router import (
    get_budget_from_travel_mcp,
    get_trip_readiness_from_mcp,
    get_trip_summary_from_mcp,
    maybe_convert_currency,
    maybe_get_weather,
)
from app.observability.tracing import (
    start_child_span,
    start_generation,
    start_root_observation,
)


def _extract_data(payload):
    if payload is None:
        return None
    return payload.get("data")


def _extract_decision(payload):
    if payload is None:
        return None
    return payload.get("_decision")


async def answer_user(
    user_query: str,
    provider: str,
    state: TravelSessionState,
    temperature: float = 0.2,
) -> dict:
    with start_root_observation(
        name="travel_turn",
        session_id=state.session_id,
        user_id=state.user_id,
        input_payload={
            "user_query": user_query,
            "provider": provider,
            "temperature": temperature,
        },
        metadata={
            "flow_stage_before": state.flow_stage,
            "state_before": state.to_dict(),
        },
        tags=["travel-copilot", provider],
    ) as root_obs:
        decision_trace = {
            "flow_stage_before": state.flow_stage,
            "steps": [],
        }

        with start_child_span(
            "parse_and_update_state",
            input_payload={"user_query": user_query},
            metadata={"step": "parse_input"},
        ) as parse_obs:
            state = update_state_from_user_query(state, user_query)
            parse_obs.update(
                output=state.to_dict(),
                metadata={"flow_stage_after_parse": state.flow_stage},
            )

        decision_trace["steps"].append(
            {
                "step": "state_update",
                "reason": "State manager parsed the user query and updated session state.",
                "flow_stage_after_parse": state.flow_stage,
                "state_snapshot": state.to_dict(),
            }
        )

        readiness_payload = None
        trip_summary_payload = None
        travel_budget_payload = None
        weather_payload = None
        currency_payload = None

        if state.flow_stage == "show_itinerary":
            decision_trace["steps"].append(
                {
                    "step": "flow_gate",
                    "reason": "flow_stage == show_itinerary, so MCP/tool lookups are allowed.",
                    "flow_stage": state.flow_stage,
                }
            )

            with start_child_span(
                "trip_readiness_lookup",
                input_payload={
                    "city": state.city,
                    "trip_days": state.trip_days,
                    "date_text": state.date_text,
                    "budget_amount": state.budget_amount,
                },
                metadata={"tool": "travel_planning_mcp.trip_readiness_check_tool"},
            ) as readiness_obs:
                readiness_payload = await get_trip_readiness_from_mcp(state)
                readiness_obs.update(output=readiness_payload)

            decision_trace["steps"].append(
                {
                    "step": "trip_readiness_lookup",
                    "decision": _extract_decision(readiness_payload),
                    "result_preview": _extract_data(readiness_payload),
                }
            )

            with start_child_span(
                "trip_summary_lookup",
                input_payload={
                    "city": state.city,
                    "trip_days": state.trip_days,
                    "date_text": state.date_text,
                    "budget_amount": state.budget_amount,
                    "budget_currency": state.budget_currency,
                    "target_currency": state.target_currency,
                },
                metadata={"tool": "travel_planning_mcp.build_trip_summary_tool"},
            ) as summary_obs:
                trip_summary_payload = await get_trip_summary_from_mcp(state)
                summary_obs.update(output=trip_summary_payload)

            decision_trace["steps"].append(
                {
                    "step": "trip_summary_lookup",
                    "decision": _extract_decision(trip_summary_payload),
                    "result_preview": _extract_data(trip_summary_payload),
                }
            )

            with start_child_span(
                "travel_budget_lookup",
                input_payload={
                    "city": state.city,
                    "trip_days": state.trip_days,
                    "budget_currency": state.budget_currency,
                    "target_currency": state.target_currency,
                },
                metadata={"tool": "travel_planning_mcp.estimate_daily_budget_tool"},
            ) as budget_obs:
                travel_budget_payload = await get_budget_from_travel_mcp(state)
                budget_obs.update(output=travel_budget_payload)

            decision_trace["steps"].append(
                {
                    "step": "travel_budget_lookup",
                    "decision": _extract_decision(travel_budget_payload),
                    "result_preview": _extract_data(travel_budget_payload),
                }
            )

            with start_child_span(
                "weather_lookup",
                input_payload={
                    "city": state.city,
                    "trip_days": state.trip_days,
                    "date_text": state.date_text,
                },
                metadata={"tool": "weather_mcp"},
            ) as weather_obs:
                synthetic_query = f"{state.city} {state.date_text or ''} {state.trip_days or ''} day weather"
                weather_payload = await maybe_get_weather(synthetic_query)
                weather_obs.update(output=weather_payload)

            decision_trace["steps"].append(
                {
                    "step": "weather_lookup",
                    "synthetic_query": synthetic_query,
                    "decision": _extract_decision(weather_payload),
                    "result_preview": _extract_data(weather_payload),
                }
            )

            with start_child_span(
                "currency_lookup",
                input_payload={
                    "budget_amount": state.budget_amount,
                    "from_currency": state.budget_currency,
                    "to_currency": state.target_currency,
                },
                metadata={"tool": "currency_mcp"},
            ) as currency_obs:
                if state.budget_amount and state.budget_currency:
                    synthetic_query = f"{state.budget_amount} {state.budget_currency}"
                    if state.target_currency:
                        synthetic_query += f" to {state.target_currency}"
                    currency_payload = await maybe_convert_currency(synthetic_query)
                else:
                    synthetic_query = None
                    currency_payload = {
                        "_decision": {
                            "mcp_family": "currency_mcp",
                            "tool_name": None,
                            "reason": "Currency lookup skipped because budget_amount or budget_currency is missing.",
                            "arguments": None,
                            "skipped": True,
                        },
                        "data": None,
                    }

                currency_obs.update(output=currency_payload)

            decision_trace["steps"].append(
                {
                    "step": "currency_lookup",
                    "synthetic_query": synthetic_query,
                    "decision": _extract_decision(currency_payload),
                    "result_preview": _extract_data(currency_payload),
                }
            )
        else:
            decision_trace["steps"].append(
                {
                    "step": "flow_gate",
                    "reason": "flow_stage is not show_itinerary, so MCP/tool lookups were skipped.",
                    "flow_stage": state.flow_stage,
                }
            )

        with start_child_span(
            "fetch_prompt",
            input_payload={"prompt_name": "travel_copilot_system"},
            metadata={"step": "prompt_fetch"},
        ) as prompt_obs:
            prompt_obj, fallback_prompt, prompt_meta = get_system_prompt()
            prompt_obs.update(output=prompt_meta)

        tool_context = {
            "trip_readiness": _extract_data(readiness_payload),
            "trip_summary": _extract_data(trip_summary_payload),
            "travel_budget": _extract_data(travel_budget_payload),
            "weather": _extract_data(weather_payload),
            "currency": _extract_data(currency_payload),
        }

        guardrails = []

        if tool_context["trip_readiness"] and tool_context["trip_readiness"].get("error"):
            guardrails.append(
                "Trip readiness lookup failed. Do not invent readiness details."
            )

        if tool_context["trip_summary"] and tool_context["trip_summary"].get("error"):
            guardrails.append(
                "Trip summary lookup failed. Do not invent trip summary details."
            )

        if tool_context["travel_budget"] and tool_context["travel_budget"].get("error"):
            guardrails.append(
                "Travel budget lookup failed. Do not invent budget estimates."
            )

        if (
            tool_context["currency"]
            and tool_context["currency"].get("converted_amount") is None
            and tool_context["currency"].get("to_currency")
        ):
            guardrails.append(
                "Currency conversion was unavailable. Do not estimate exchange rates."
            )

        if tool_context["weather"] and tool_context["weather"].get("error"):
            guardrails.append(
                "Weather lookup failed. Do not invent weather conditions."
            )

        prompt_variables = {
            "session_state": str(state.to_dict()),
            "user_request": user_query,
            "tool_context": str(tool_context),
            "guardrails": str(guardrails),
        }

        if prompt_obj is not None and hasattr(prompt_obj, "get_langchain_prompt"):
            langchain_prompt = PromptTemplate.from_template(
                prompt_obj.get_langchain_prompt(),
                metadata={"langfuse_prompt": prompt_obj},
            )
        else:
            langchain_prompt = PromptTemplate.from_template(fallback_prompt)

        llm = get_chat_model(provider=provider, temperature=temperature)
        chain = langchain_prompt | llm
        langfuse_handler = CallbackHandler()

        with start_generation(
            name="llm_generation",
            model=getattr(llm, "model_name", None) or getattr(llm, "model", "unknown"),
            input_payload={
                "prompt_variables": prompt_variables,
                "provider": provider,
            },
            metadata={
                "provider": provider,
                "flow_stage": state.flow_stage,
                **prompt_meta,
            },
            prompt=prompt_obj,
        ) as gen_obs:
            response = chain.invoke(
                prompt_variables,
                config={
                    "callbacks": [langfuse_handler],
                    "run_name": "travel_itinerary_generation",
                },
            )

            answer = response.content if hasattr(response, "content") else str(response)

            usage = None
            response_metadata = getattr(response, "response_metadata", {}) or {}
            if "token_usage" in response_metadata:
                usage = response_metadata["token_usage"]

            update_payload = {
                "output": {"answer": answer},
            }
            if usage:
                update_payload["usage_details"] = usage

            gen_obs.update(**update_payload)

        decision_trace["flow_stage_after"] = state.flow_stage
        decision_trace["llm_input_summary"] = {
            "tool_context_keys": list(tool_context.keys()),
            "guardrails": guardrails,
        }

        if root_obs:
            root_obs.update(
                output={
                    "answer": answer,
                    "state_after": state.to_dict(),
                    "tool_context": tool_context,
                    "decision_trace": decision_trace,
                    "prompt_meta": prompt_meta,
                },
                metadata={
                    "flow_stage_after": state.flow_stage,
                    "city": state.city,
                    "trip_days": state.trip_days,
                    "budget_currency": state.budget_currency,
                    "target_currency": state.target_currency,
                },
            )

        return {
            "answer": answer,
            "tool_context": tool_context,
            "decision_trace": decision_trace,
            "state": state.to_dict(),
            "flow_stage": state.flow_stage,
            "prompt_meta": prompt_meta,
        }