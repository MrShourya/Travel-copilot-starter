from langchain_core.prompts import PromptTemplate
from langfuse.langchain import CallbackHandler

from datetime import datetime, timedelta

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


# -----------------------------
# 🔧 SAFETY: derive dates if missing
# -----------------------------
def _ensure_dates(state: TravelSessionState):
    if state.start_date:
        return

    if not state.date_text:
        return

    try:
        start_dt = datetime.strptime(state.date_text, "%Y-%m-%d").date()
    except Exception:
        return

    state.start_date = start_dt.isoformat()

    if state.trip_days:
        end_dt = start_dt + timedelta(days=state.trip_days - 1)
        state.end_date = end_dt.isoformat()


def _extract_data(payload):
    if payload is None:
        return None
    return payload.get("data")


def _extract_decision(payload):
    if payload is None:
        return None
    return payload.get("_decision")


# -----------------------------
# 🚀 MAIN FUNCTION
# -----------------------------
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

        # -----------------------------
        # STEP 1: Update state
        # -----------------------------
        with start_child_span(
            "parse_and_update_state",
            input_payload={"user_query": user_query},
        ) as parse_obs:
            state = update_state_from_user_query(state, user_query)

            # ✅ ensure normalized dates always exist if possible
            _ensure_dates(state)

            parse_obs.update(output=state.to_dict())

        # -----------------------------
        # TOOL EXECUTION
        # -----------------------------
        readiness_payload = None
        trip_summary_payload = None
        travel_budget_payload = None
        weather_payload = None
        currency_payload = None

        if state.flow_stage == "show_itinerary":

            # -----------------------------
            # Trip readiness
            # -----------------------------
            readiness_payload = await get_trip_readiness_from_mcp(state)

            # -----------------------------
            # Trip summary
            # -----------------------------
            trip_summary_payload = await get_trip_summary_from_mcp(state)

            # -----------------------------
            # Budget
            # -----------------------------
            travel_budget_payload = await get_budget_from_travel_mcp(state)

            # -----------------------------
            # 🌦 WEATHER (FIXED)
            # -----------------------------
            if state.start_date:
                synthetic_query = f"{state.city} {state.start_date} to {state.end_date}"
            else:
                synthetic_query = f"{state.city} {state.date_text or ''}"

            weather_payload = await maybe_get_weather(synthetic_query)

            # -----------------------------
            # Currency
            # -----------------------------
            if state.budget_amount and state.budget_currency:
                synthetic_query = f"{state.budget_amount} {state.budget_currency}"
                if state.target_currency:
                    synthetic_query += f" to {state.target_currency}"

                currency_payload = await maybe_convert_currency(synthetic_query)
            else:
                currency_payload = None

        # -----------------------------
        # TOOL CONTEXT
        # -----------------------------
        tool_context = {
            "trip_readiness": _extract_data(readiness_payload),
            "trip_summary": _extract_data(trip_summary_payload),
            "travel_budget": _extract_data(travel_budget_payload),
            "weather": _extract_data(weather_payload),
            "currency": _extract_data(currency_payload),
        }

        # -----------------------------
        # PROMPT
        # -----------------------------
        prompt_obj, fallback_prompt, prompt_meta = get_system_prompt()

        prompt_variables = {
            "session_state": str(state.to_dict()),
            "user_request": user_query,
            "tool_context": str(tool_context),
            "guardrails": "[]",
        }

        if prompt_obj and hasattr(prompt_obj, "get_langchain_prompt"):
            langchain_prompt = PromptTemplate.from_template(
                prompt_obj.get_langchain_prompt(),
                metadata={"langfuse_prompt": prompt_obj},
            )
        else:
            langchain_prompt = PromptTemplate.from_template(fallback_prompt)

        llm = get_chat_model(provider=provider, temperature=temperature)
        chain = langchain_prompt | llm
        handler = CallbackHandler()

        # -----------------------------
        # LLM CALL
        # -----------------------------
        with start_generation(
            name="llm_generation",
            model=getattr(llm, "model_name", "unknown"),
            input_payload={"prompt_variables": prompt_variables},
        ) as gen_obs:

            response = chain.invoke(
                prompt_variables,
                config={"callbacks": [handler]},
            )

            answer = response.content if hasattr(response, "content") else str(response)

            gen_obs.update(output={"answer": answer})

        # -----------------------------
        # FINAL RESPONSE
        # -----------------------------
        if root_obs:
            root_obs.update(
                output={
                    "answer": answer,
                    "state_after": state.to_dict(),
                    "tool_context": tool_context,
                }
            )

        return {
            "answer": answer,
            "tool_context": tool_context,
            "state": state.to_dict(),
            "flow_stage": state.flow_stage,
            "prompt_meta": prompt_meta,
        }