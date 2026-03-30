from contextlib import nullcontext

from langfuse import get_client, propagate_attributes


def get_langfuse():
    try:
        return get_client()
    except Exception as exc:
        print(f"[Langfuse] Failed to initialize client: {exc}")
        return None


def start_root_observation(
    *,
    name: str,
    session_id: str,
    user_id: str,
    input_payload: dict,
    metadata: dict | None = None,
    tags: list[str] | None = None,
):
    langfuse = get_langfuse()
    if not langfuse:
        return nullcontext()

    attr_ctx = propagate_attributes(
        session_id=session_id,
        user_id=user_id,
        metadata=metadata or {},
        tags=tags or [],
    )

    obs_ctx = langfuse.start_as_current_observation(
        name=name,
        as_type="span",
        input=input_payload,
    )

    class CombinedContext:
        def __enter__(self):
            self._attr = attr_ctx.__enter__()
            self._obs = obs_ctx.__enter__()
            return self._obs

        def __exit__(self, exc_type, exc, tb):
            obs_ctx.__exit__(exc_type, exc, tb)
            attr_ctx.__exit__(exc_type, exc, tb)

    return CombinedContext()


def start_child_span(name: str, input_payload: dict | None = None, metadata: dict | None = None):
    langfuse = get_langfuse()
    if not langfuse:
        return nullcontext()

    return langfuse.start_as_current_observation(
        name=name,
        as_type="span",
        input=input_payload or {},
        metadata=metadata or {},
    )