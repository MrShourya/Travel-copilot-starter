from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from app.config.settings import settings


def get_chat_model(provider: str, temperature: float = 0.2):
    provider = provider.lower().strip()

    if provider == "openai":
        return ChatOpenAI(
            model=settings.openai_model,
            temperature=temperature,
        )

    if provider == "ollama":
        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=temperature,
        )

    raise ValueError(f"Unsupported provider: {provider}")