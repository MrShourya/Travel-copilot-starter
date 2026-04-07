from pathlib import Path
import sys

from dotenv import load_dotenv
import streamlit as st

from app.config.settings import settings
from app.ui.deterministic_page import render_page as render_deterministic_page
from app.ui.dynamic_mcp_page import render_page as render_dynamic_page
from app.ui.ui_state import ensure_ui_state

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


st.set_page_config(page_title="Travel Copilot", page_icon="✈️", layout="wide")
st.title("✈️ Multi-LLM Travel Copilot")

ensure_ui_state()

with st.sidebar:
    st.header("Settings")
    provider = st.selectbox(
        "Model provider",
        options=["openai", "ollama"],
        index=0 if settings.default_model_provider == "openai" else 1,
    )
    temperature = st.slider("Temperature", 0.0, 1.0, 0.2, 0.1)

    st.subheader("Session")
    session_placeholder = st.empty()
    session_placeholder.json(st.session_state.travel_state.to_dict())

tab_det, tab_dyn = st.tabs(["Deterministic MCP", "Dynamic MCP Lab"])

with tab_det:
    render_deterministic_page(
        provider=provider,
        temperature=temperature,
        session_placeholder=session_placeholder,
    )

with tab_dyn:
    render_dynamic_page(
        provider=provider,
        temperature=temperature,
        session_placeholder=session_placeholder,
    )