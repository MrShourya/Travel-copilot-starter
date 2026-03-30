from pathlib import Path
import sys
import uuid
import asyncio

from dotenv import load_dotenv
load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from app.chat.agent import answer_user
from app.chat.session_state import TravelSessionState
from app.config.settings import settings

st.set_page_config(page_title="Travel Copilot", page_icon="✈️", layout="wide")
st.title("✈️ Multi-LLM Travel Copilot")

if "travel_session_id" not in st.session_state:
    st.session_state.travel_session_id = f"travel-{uuid.uuid4().hex[:12]}"

if "travel_user_id" not in st.session_state:
    st.session_state.travel_user_id = "local-user"

if "travel_state" not in st.session_state:
    st.session_state.travel_state = TravelSessionState(
        session_id=st.session_state.travel_session_id,
        user_id=st.session_state.travel_user_id,
    )

if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.header("Settings")
    provider = st.selectbox(
        "Model provider",
        options=["openai", "ollama"],
        index=0 if settings.default_model_provider == "openai" else 1,
    )
    temperature = st.slider("Temperature", 0.0, 1.0, 0.2, 0.1)

    st.subheader("Session")
    st.code(st.session_state.travel_session_id)
    st.json(st.session_state.travel_state.to_dict())

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_input = st.chat_input("Ask about your trip...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            result = asyncio.run(
                answer_user(
                    user_query=user_input,
                    provider=provider,
                    state=st.session_state.travel_state,
                    temperature=temperature,
                )
            )

            # rebuild dataclass instance from returned dict
            state_dict = result["state"]
            st.session_state.travel_state = TravelSessionState(**state_dict)

            st.markdown(result["answer"])

            with st.expander("Tool context"):
                st.json(result["tool_context"])

            with st.expander("Session state"):
                st.json(result["state"])

    st.session_state.messages.append(
        {"role": "assistant", "content": result["answer"]}
    )