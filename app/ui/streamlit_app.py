from pathlib import Path
import sys

from dotenv import load_dotenv
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import settings
from app.ui.deterministic_page import render_page as render_deterministic_page
from app.ui.dynamic_mcp_page import render_page as render_dynamic_page
from app.ui.ui_state import ensure_ui_state

load_dotenv()

st.set_page_config(page_title="Travel Copilot", page_icon="✈️", layout="wide")
st.title("✈️ Multi-MCP Travel Copilot")
st.caption(
        "We connect tools using Stdio (currency tools), HTTP (weather tools), own custom MCP tools over HTTP (travel-planning-mcp)."
    )
st.markdown(
    """
    <style>
    html, body, [data-testid="stAppViewContainer"] {
        height: 100%;
    }

    .main .block-container {
        padding-bottom: 120px;
    }

    div[data-testid="stChatInput"] {
        position: fixed !important;
        bottom: 0;
        left: 0;
        right: 0;
        z-index: 9999;
        padding: 12px 20px 14px 20px;
        background: var(--background-color);
        border-top: 1px solid rgba(128, 128, 128, 0.25);
        box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.12);
    }

    div[data-testid="stChatInput"] > div {
        width: min(1100px, calc(100vw - 40px)) !important;
        max-width: 1100px !important;
        margin: 0 auto !important;
    }

    div[data-testid="stChatInput"] textarea,
    div[data-testid="stChatInput"] input {
        background-color: transparent !important;
        color: inherit !important;
        caret-color: inherit !important;
    }

    div[data-testid="stChatInput"] textarea::placeholder,
    div[data-testid="stChatInput"] input::placeholder {
        color: rgba(127, 127, 127, 0.9) !important;
        opacity: 1 !important;
    }

    div[data-testid="stChatInput"] [data-baseweb="textarea"],
    div[data-testid="stChatInput"] [data-baseweb="input"] {
        background: transparent !important;
        color: inherit !important;
    }

    div[data-testid="stChatInput"] [data-baseweb="textarea"] *,
    div[data-testid="stChatInput"] [data-baseweb="input"] * {
        color: inherit !important;
    }

    div[data-testid="stChatInput"] button {
        background: transparent !important;
    }

    @media (prefers-color-scheme: dark) {
        div[data-testid="stChatInput"] {
            background: #0e1117 !important;
            border-top: 1px solid rgba(255, 255, 255, 0.08);
            box-shadow: 0 -2px 12px rgba(0, 0, 0, 0.45);
        }

        div[data-testid="stChatInput"] textarea,
        div[data-testid="stChatInput"] input,
        div[data-testid="stChatInput"] [data-baseweb="textarea"],
        div[data-testid="stChatInput"] [data-baseweb="input"] {
            color: #fafafa !important;
            caret-color: #fafafa !important;
        }

        div[data-testid="stChatInput"] textarea::placeholder,
        div[data-testid="stChatInput"] input::placeholder {
            color: rgba(255, 255, 255, 0.55) !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

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

# Dynamic first = default selected tab
tab_dyn, tab_det = st.tabs(["Dynamic MCP Lab", "Deterministic MCP"])

with tab_dyn:
    render_dynamic_page(
        provider=provider,
        temperature=temperature,
        session_placeholder=session_placeholder,
    )

with tab_det:
    render_deterministic_page(
        provider=provider,
        temperature=temperature,
        session_placeholder=session_placeholder,
    )