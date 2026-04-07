import asyncio

import streamlit as st

from app.chat.agent import answer_user
from app.chat.session_state import TravelSessionState
from app.ui.rendering_common import render_json_expander, render_markdown_with_table

def _step_status_icon(step: dict) -> str:
    decision = step.get("decision", {})
    result = step.get("result_preview")

    if decision and decision.get("skipped"):
        return "🟡"

    if isinstance(result, dict) and result.get("error"):
        return "🔴"

    return "🟢"


def _step_label(step: dict) -> str:
    step_name = step.get("step", "")

    mapping = {
        "state_update": "State",
        "flow_gate": "Flow Gate",
        "trip_readiness_lookup": "Readiness",
        "trip_summary_lookup": "Trip Summary",
        "travel_budget_lookup": "Budget",
        "weather_lookup": "Weather",
        "currency_lookup": "Currency",
    }

    return mapping.get(step_name, step_name.replace("_", " ").title())


def _render_step_detail(step: dict) -> None:
    step_name = step.get("step", "")
    decision = step.get("decision", {})
    result = step.get("result_preview")

    if step_name == "state_update":
        st.markdown("### 🧠 State Parsing")
        st.write("The app first extracted structured travel information from your message.")
        st.write("**Flow stage after parse:**", step.get("flow_stage_after_parse"))

        state = step.get("state_snapshot")
        if state:
            st.json(state)
        return

    if step_name == "flow_gate":
        st.markdown("### 🚦 Flow Gate")
        st.write(step.get("reason", ""))
        if step.get("flow_stage"):
            st.write("**Flow stage:**", step.get("flow_stage"))
        return

    st.markdown(f"### {_step_label(step)}")

    if decision:
        st.write("**Why this step happened:**")
        st.info(decision.get("reason", "No reason captured."))

        st.write("**MCP family:**", decision.get("mcp_family"))
        st.write("**Tool selected:**", decision.get("tool_name"))
        st.write("**Skipped:**", decision.get("skipped"))

        if decision.get("arguments") is not None:
            with st.expander("Arguments sent to MCP", expanded=False):
                st.json(decision.get("arguments"))

    if step.get("synthetic_query"):
        st.write("**Synthetic query built by Python:**")
        st.code(step["synthetic_query"], language="text")

    if result is not None:
        with st.expander("Returned payload", expanded=True):
            st.json(result)


def render_decision_trace(decision_trace: dict | None) -> None:
    if not decision_trace:
        st.info("No decision trace available.")
        return

    steps = decision_trace.get("steps", [])
    if not steps:
        st.info("No decision steps were recorded.")
        return

    st.markdown("## 🧭 Decision Flow")

    # Horizontal visual summary
    cols = st.columns(len(steps))
    for idx, step in enumerate(steps):
        icon = _step_status_icon(step)
        label = _step_label(step)

        with cols[idx]:
            st.markdown(
                f"""
<div style="text-align:center; padding:10px; border:1px solid #ddd; border-radius:12px; min-height:90px;">
    <div style="font-size:28px;">{icon}</div>
    <div style="font-weight:600;">{label}</div>
    <div style="font-size:12px; color:gray;">Step {idx + 1}</div>
</div>
""",
                unsafe_allow_html=True,
            )

    st.markdown("")
    st.caption("Move left to right through the execution steps below.")

    # Tabs per step
    tab_labels = [f"{_step_status_icon(step)} {_step_label(step)}" for step in steps]
    tabs = st.tabs(tab_labels)

    for tab, step in zip(tabs, steps):
        with tab:
            _render_step_detail(step)

    with st.expander("🧪 Full Raw Trace (Debug)", expanded=False):
        st.json(decision_trace)

def render_assistant_message(msg: dict) -> None:
    render_markdown_with_table(msg["content"])

    if msg.get("decision_trace") is not None:
        with st.expander("How the app decided which MCP tools to call", expanded=False):
            render_decision_trace(msg["decision_trace"])

    render_json_expander("Tool context", msg.get("tool_context"))
    render_json_expander("Session state", msg.get("state"))
    render_json_expander("Prompt metadata", msg.get("prompt_meta"))


def render_page(*, provider: str, temperature: float, session_placeholder) -> None:
    st.subheader("Deterministic / Python-routed MCP")
    st.caption("Python decides which MCP tools to call. The LLM only sees the resulting tool context.")

    for msg in st.session_state.messages_deterministic:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                render_assistant_message(msg)
            else:
                st.markdown(msg["content"])

    user_input = st.chat_input("Ask about your trip...", key="chat_input_deterministic")

    if not user_input:
        return

    st.session_state.messages_deterministic.append(
        {"role": "user", "content": user_input}
    )

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
                "message_id": f"dynamic_{len(st.session_state.messages_dynamic)}",
                "role": "assistant",
                "content": result["answer"],
                "response_type": result.get("response_type"),
                "decision_trace": result.get("decision_trace"),
                "tool_results": result.get("tool_results"),
                "state": result.get("state"),
            }

            render_assistant_message(assistant_message)

    st.session_state.messages_deterministic.append(assistant_message)