from app.observability.langfuse_client import get_langfuse_client

DEFAULT_SYSTEM_PROMPT = """
You are a travel copilot.

Rules:
- Preserve previously confirmed session details unless the user changes them.
- If a tool fails or returns incomplete data, say so clearly.
- Do not invent weather, exchange rates, prices, or factual tool outputs.
- Only use currency conversion when the user explicitly asks for a target currency.
- If no target currency is specified, keep the original currency unchanged.
- If the flow stage is "show_itinerary", present the itinerary as a markdown table with columns:
  Day | Morning | Afternoon | Evening | Notes

Current session state:
{session_state}

User request:
{user_request}

Tool context:
{tool_context}

Guardrails:
{guardrails}

Respond with these sections:
1. Current understanding
2. Trip summary
3. Suggested itinerary
4. Budget notes
5. Weather considerations
6. Assumptions / missing information
""".strip()


def get_system_prompt():
    client = get_langfuse_client()
    if not client:
        return None, DEFAULT_SYSTEM_PROMPT, {
            "prompt_name": "default_fallback",
            "prompt_source": "local",
        }

    try:
        prompt = client.get_prompt("travel_copilot_system")
        compiled_preview = prompt.compile(
            session_state="",
            user_request="",
            tool_context="",
            guardrails="",
        )

        meta = {
            "prompt_name": "travel_copilot_system",
            "prompt_source": "langfuse",
        }

        if hasattr(prompt, "version"):
            meta["prompt_version"] = prompt.version
        if hasattr(prompt, "labels"):
            meta["prompt_labels"] = prompt.labels
        if hasattr(prompt, "config"):
            meta["prompt_config"] = prompt.config

        return prompt, compiled_preview, meta

    except Exception as exc:
        print(f"[Langfuse] Failed to load prompt: {exc}")
        return None, DEFAULT_SYSTEM_PROMPT, {
            "prompt_name": "default_fallback",
            "prompt_source": "local",
            "prompt_error": str(exc),
        }