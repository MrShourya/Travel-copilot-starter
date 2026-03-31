from langchain_core.prompts import PromptTemplate
from langfuse.langchain import CallbackHandler

from app.chat.model_factory import get_chat_model
from app.chat.prompt_loader import get_system_prompt
from app.chat.session_state import TravelSessionState
from app.chat.state_manager import update_state_from_user_query
from app.chat.tool_router import maybe_convert_currency, maybe_get_weather
from app.observability.tracing import (
    start_child_span,
    start_generation,
    start_root_observation,
)


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

        weather_context = None
        currency_context = None

        if state.flow_stage == "show_itinerary":
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
                weather_context = await maybe_get_weather(synthetic_query)
                weather_obs.update(output=weather_context)

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
                    currency_context = await maybe_convert_currency(synthetic_query)
                currency_obs.update(output=currency_context)

        with start_child_span(
            "fetch_prompt",
            input_payload={"prompt_name": "travel_copilot_system"},
            metadata={"step": "prompt_fetch"},
        ) as prompt_obs:
            prompt_obj, fallback_prompt, prompt_meta = get_system_prompt()
            prompt_obs.update(output=prompt_meta)

        tool_context = {
            "weather": weather_context,
            "currency": currency_context,
        }

        guardrails = []
        if (
            currency_context
            and currency_context.get("converted_amount") is None
            and currency_context.get("to_currency")
        ):
            guardrails.append(
                "Currency conversion was unavailable. Do not estimate exchange rates."
            )
        if weather_context and weather_context.get("error"):
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
            "prompt_meta": prompt_meta,
        }