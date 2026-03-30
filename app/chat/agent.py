from app.chat.model_factory import get_chat_model
from app.chat.prompt_loader import get_system_prompt
from app.chat.session_state import TravelSessionState
from app.chat.state_manager import update_state_from_user_query
from app.chat.tool_router import maybe_convert_currency, maybe_get_weather
from app.observability.tracing import start_child_span, start_root_observation


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
        with start_child_span("parse_and_update_state", {"user_query": user_query}):
            state = update_state_from_user_query(state, user_query)

        weather_context = None
        currency_context = None

        if state.flow_stage == "show_itinerary":
            with start_child_span(
                "weather_lookup",
                metadata={
                    "city": state.city,
                    "trip_days": state.trip_days,
                    "date_text": state.date_text,
                },
            ):
                synthetic_query = f"{state.city} {state.date_text or ''} {state.trip_days or ''} day weather"
                weather_context = await maybe_get_weather(synthetic_query)

            with start_child_span(
                "currency_lookup",
                metadata={
                    "budget_amount": state.budget_amount,
                    "from_currency": state.budget_currency,
                    "to_currency": state.target_currency,
                },
            ):
                if state.budget_amount and state.budget_currency:
                    synthetic_query = f"{state.budget_amount} {state.budget_currency}"
                    if state.target_currency:
                        synthetic_query += f" to {state.target_currency}"
                    currency_context = await maybe_convert_currency(synthetic_query)

        with start_child_span("fetch_prompt"):
            system_prompt, prompt_meta = get_system_prompt()

        tool_context = {
            "weather": weather_context,
            "currency": currency_context,
        }

        guardrails = []
        if currency_context and currency_context.get("converted_amount") is None and currency_context.get("to_currency"):
            guardrails.append("Currency conversion was unavailable. Do not estimate exchange rates.")
        if weather_context and weather_context.get("error"):
            guardrails.append("Weather lookup failed. Do not invent weather conditions.")

        llm_input = f"""
{system_prompt}

Current session state:
{state.to_dict()}

User request:
{user_query}

Tool context:
{tool_context}

Guardrails:
{guardrails}
""".strip()

        with start_child_span(
            "llm_generation",
            metadata={
                "provider": provider,
                "prompt_meta": prompt_meta,
                "flow_stage": state.flow_stage,
            },
        ):
            llm = get_chat_model(provider=provider, temperature=temperature)
            response = llm.invoke(llm_input)
            answer = response.content if hasattr(response, "content") else str(response)

        if root_obs:
            root_obs.update(
                output={
                    "answer": answer,
                    "state_after": state.to_dict(),
                    "tool_context": tool_context,
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
            "state": state.to_dict(),
            "flow_stage": state.flow_stage,
        }