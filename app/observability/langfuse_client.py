from langfuse import get_client


def get_langfuse_client():
    try:
        return get_client()
    except Exception as exc:
        print(f"[Langfuse] Failed to initialize client: {exc}")
        return None