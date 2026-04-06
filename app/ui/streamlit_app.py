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
from app.ui.rendering import extract_first_markdown_table


def render_decision_trace(decision_trace: dict | None) -> None:
    if not decision_trace:
        st.info("No decision trace available for this turn.")
        return

    st.write(f"**Flow stage before:** {decision_trace.get('flow_stage_before')}")
    st.write(f"**Flow stage after:** {decision_trace.get('flow_stage_after')}")

    llm_summary = decision_trace.get("llm_input_summary")
    if llm_summary:
        with st.expander("What was sent to the LLM", expanded=False):
            st.write("**Tool context keys:**", llm_summary.get("tool_context_keys"))
            st.write("**Guardrails:**")
            st.json(llm_summary.get("guardrails", []))

    steps = decision_trace.get("steps", [])
    if not steps:
        st.info("No decision steps were recorded.")
        return

    for idx, step in enumerate(steps, start=1):
        title = f"Step {idx}: {step.get('step', 'unknown_step')}"
        with st.container(border=True):
            st.markdown(f"### {title}")

            if step.get("reason"):
                st.write("**Reason:**", step["reason"])

            if step.get("flow_stage_after_parse"):
                st.write("**Flow stage after parse:**", step["flow_stage_after_parse"])

            if step.get("flow_stage"):
                st.write("**Flow stage:**", step["flow_stage"])

            if step.get("synthetic_query"):
                st.write("**Synthetic query built by Python:**")
                st.code(step["synthetic_query"], language="text")

            if step.get("state_snapshot") is not None:
                with st.expander("State snapshot at this step", expanded=False):
                    st.json(step["state_snapshot"])

            decision = step.get("decision")
            if decision:
                st.write("**MCP family:**", decision.get("mcp_family"))
                st.write("**Tool selected:**", decision.get("tool_name"))
                st.write("**Skipped:**", decision.get("skipped"))
                st.write("**Decision reason:**", decision.get("reason"))

                if decision.get("arguments") is not None:
                    with st.expander("Arguments sent to MCP", expanded=False):
                        st.json(decision["arguments"])

            if step.get("result_preview") is not None:
                with st.expander("Returned payload", expanded=False):
                    st.json(step["result_preview"])


def render_assistant_message(msg: dict) -> None:
    table_df = extract_first_markdown_table(msg["content"])
    if table_df is not None:
        st.table(table_df)

    st.markdown(msg["content"])

    if msg.get("decision_trace") is not None:
        with st.expander("How the app decided which MCP tools to call", expanded=False):
            render_decision_trace(msg["decision_trace"])

    if msg.get("tool_context") is not None:
        with st.expander("Tool context", expanded=False):
            st.json(msg["tool_context"])

    if msg.get("state") is not None:
        with st.expander("Session state", expanded=False):
            st.json(msg["state"])

    if msg.get("prompt_meta") is not None:
        with st.expander("Prompt metadata", expanded=False):
            st.json(msg["prompt_meta"])


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
    session_placeholder = st.empty()
    session_placeholder.json(st.session_state.travel_state.to_dict())

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            render_assistant_message(msg)
        else:
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

            state_dict = result["state"]
            st.session_state.travel_state = TravelSessionState(**state_dict)

            session_placeholder.json(st.session_state.travel_state.to_dict())

            assistant_message = {
                "role": "assistant",
                "content": result["answer"],
                "tool_context": result.get("tool_context"),
                "decision_trace": result.get("decision_trace"),
                "state": result.get("state"),
                "prompt_meta": result.get("prompt_meta"),
            }

            render_assistant_message(assistant_message)

    st.session_state.messages.append(assistant_message)