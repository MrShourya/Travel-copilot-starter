from contextlib import nullcontext

from langfuse import propagate_attributes

from app.observability.langfuse_client import get_langfuse_client


class _CombinedContext:
    def __init__(self, attr_ctx, obs_ctx, input_payload=None, metadata=None):
        self.attr_ctx = attr_ctx
        self.obs_ctx = obs_ctx
        self.input_payload = input_payload or {}
        self.metadata = metadata or {}
        self.obs = None

    def __enter__(self):
        self.attr_ctx.__enter__()
        self.obs = self.obs_ctx.__enter__()
        self.obs.update(
            input=self.input_payload,
            metadata=self.metadata,
        )
        return self.obs

    def __exit__(self, exc_type, exc, tb):
        self.obs_ctx.__exit__(exc_type, exc, tb)
        self.attr_ctx.__exit__(exc_type, exc, tb)


class _ObservationContext:
    def __init__(self, obs_ctx, input_payload=None, metadata=None):
        self.obs_ctx = obs_ctx
        self.input_payload = input_payload or {}
        self.metadata = metadata or {}
        self.obs = None

    def __enter__(self):
        self.obs = self.obs_ctx.__enter__()
        self.obs.update(
            input=self.input_payload,
            metadata=self.metadata,
        )
        return self.obs

    def __exit__(self, exc_type, exc, tb):
        self.obs_ctx.__exit__(exc_type, exc, tb)


def start_root_observation(
    *,
    name: str,
    session_id: str,
    user_id: str,
    input_payload: dict,
    metadata: dict | None = None,
    tags: list[str] | None = None,
):
    langfuse = get_langfuse_client()
    if not langfuse:
        return nullcontext()

    attr_ctx = propagate_attributes(
        session_id=session_id,
        user_id=user_id,
        metadata=metadata or {},
        tags=tags or [],
    )
    obs_ctx = langfuse.start_as_current_observation(
        as_type="span",
        name=name,
    )
    return _CombinedContext(attr_ctx, obs_ctx, input_payload, metadata)


def start_child_span(
    name: str,
    input_payload: dict | None = None,
    metadata: dict | None = None,
):
    langfuse = get_langfuse_client()
    if not langfuse:
        return nullcontext()

    obs_ctx = langfuse.start_as_current_observation(
        as_type="span",
        name=name,
    )
    return _ObservationContext(obs_ctx, input_payload, metadata)


def start_generation(
    name: str,
    model: str,
    input_payload: dict | None = None,
    metadata: dict | None = None,
    prompt=None,
):
    langfuse = get_langfuse_client()
    if not langfuse:
        return nullcontext()

    kwargs = {
        "as_type": "generation",
        "name": name,
        "model": model,
    }
    if prompt is not None:
        kwargs["prompt"] = prompt

    obs_ctx = langfuse.start_as_current_observation(**kwargs)
    return _ObservationContext(obs_ctx, input_payload, metadata)