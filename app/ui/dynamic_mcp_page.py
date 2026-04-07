import asyncio

import streamlit as st

from app.chat.dynamic_mcp.agent import answer_user_dynamic
from app.chat.session_state import TravelSessionState
from app.ui.rendering_common import render_json_expander, render_markdown_with_table


def render_dynamic_trace(decision_trace: list[dict] | None) -> None:
    if not decision_trace:
        st.info("No workflow trace available for this turn.")
        return

    stage_map = {
        "turn_start": "1. User Input",
        "input_understanding": "2. Input Understanding",
        "state_extraction": "3. Extraction",
        "planner_input": "4. Planner Context",
        "planner_prompt": "5. Planner Prompt",
        "planner_response": "6. Planner Response",
        "planner_decision": "7. Parsed Decision",
        "input_requirements_check": "8. Input Requirements",
        "validation": "9. Validation",
        "validation_failed": "10. Missing Inputs",
        "ask_user": "11. Ask User",
        "tool_pre_execution": "12. Tool Preparation",
        "tool_execution": "13. Tool Execution",
        "tool_execution_failed": "14. Tool Failure",
        "final_answer": "15. Final Answer",
        "planner_error": "Planner Error",
        "loop_limit": "Loop Limit",
    }

    visible_steps = []
    labels = []

    for step in decision_trace:
        step_type = step.get("step_type", "unknown")
        label = stage_map.get(step_type, step_type)
        visible_steps.append(step)
        labels.append(label)

    st.markdown("## 🧭 Workflow Movement")

    ribbon_cols = st.columns(len(labels))
    for col, label, step in zip(ribbon_cols, labels, visible_steps):
        step_type = step.get("step_type", "")
        icon = "🟢"
        if step_type in {"validation_failed", "planner_error", "tool_execution_failed"}:
            icon = "🔴"
        elif step_type in {"ask_user", "loop_limit"}:
            icon = "🟡"

        with col:
            st.markdown(
                f"""
<div style="text-align:center; padding:8px; border:1px solid #ddd; border-radius:12px; min-height:80px;">
    <div style="font-size:24px;">{icon}</div>
    <div style="font-size:13px; font-weight:600;">{label}</div>
</div>
""",
                unsafe_allow_html=True,
            )

    tabs = st.tabs(labels)

    for tab, step in zip(tabs, visible_steps):
        with tab:
            step_type = step.get("step_type")
            payload = step.get("payload", {})

            if step_type == "turn_start":
                st.markdown("### 📝 Raw User Input")
                st.write(payload.get("user_query"))
                st.write("**Provider:**", payload.get("provider"))
                render_json_expander("State before turn", payload.get("state_before"))

            elif step_type == "input_understanding":
                st.markdown("### 🔍 How the app read the input text")
                analysis = payload.get("input_analysis", {})
                st.write("**Raw text:**", analysis.get("raw_text"))
                st.write("**Normalized text:**", analysis.get("normalized_text"))
                render_json_expander("Detected intent hints", analysis.get("keyword_hints"), expanded=True)

            elif step_type == "state_extraction":
                st.markdown("### 🧩 Structured values extracted from the input")
                st.write("These values are what the rest of the workflow can use.")
                st.json(payload.get("extracted_slots"))

            elif step_type == "planner_input":
                st.markdown("### 📚 What context was given to the planner")
                st.json(payload.get("planner_input"))

            elif step_type == "planner_prompt":
                st.markdown("### 🧠 Prompt sent to the planner LLM")
                st.text_area(
                    "Rendered planner prompt",
                    value=payload.get("prompt_text", ""),
                    height=350,
                    disabled=True,
                )

            elif step_type == "planner_response":
                st.markdown("### 🤖 Raw response returned by the planner LLM")
                st.code(payload.get("raw_response", ""), language="json")
                st.write("**Parsed decision:**")
                st.json(payload.get("parsed_decision"))

            elif step_type == "planner_decision":
                st.markdown("### 🎯 Interpreted planner decision")
                st.json(payload.get("decision"))

            elif step_type == "input_requirements_check":
                st.markdown("### 📋 Required inputs vs available inputs")
                explanation = payload.get("validation_explanation", {})
                st.write("**Tool/action selected:**", explanation.get("tool_name"))
                st.write("**Required inputs:**", explanation.get("required_args"))
                st.write("**Provided inputs:**")
                st.json(explanation.get("provided_args"))
                st.write("**Missing inputs:**", explanation.get("missing_args"))

            elif step_type == "validation":
                st.markdown("### ✅ Can this step be executed?")
                st.json(payload.get("validation"))

            elif step_type == "validation_failed":
                st.markdown("### ❓ Why the app could not execute the tool yet")
                st.error(payload.get("error", "Validation failed"))
                st.write("**Missing fields:**", payload.get("missing_fields"))
                st.write("**Question generated for the user:**")
                st.info(payload.get("generated_question"))

            elif step_type == "ask_user":
                st.markdown("### 💬 Follow-up question to the user")
                st.write("**Reason:**", payload.get("reason"))
                st.info(payload.get("question"))

            elif step_type == "tool_pre_execution":
                st.markdown("### 🛠 Tool selected for execution")
                st.write("**MCP family:**", payload.get("mcp_family"))
                st.write("**Tool name:**", payload.get("tool_name"))
                st.write("**Why this tool was chosen:**", payload.get("reason"))
                render_json_expander("Arguments", payload.get("arguments"), expanded=True)
                render_json_expander("Where each argument came from", payload.get("argument_provenance"), expanded=True)

            elif step_type == "tool_execution":
                st.markdown("### 📦 Tool execution result")
                st.json(payload.get("execution", {}))

            elif step_type == "tool_execution_failed":
                st.markdown("### ❌ Tool execution failed")
                st.error(payload.get("fallback_answer"))

            elif step_type == "final_answer":
                st.markdown("### ✅ Final system response")
                st.write("**Reason:**", payload.get("reason"))
                st.success(payload.get("answer"))

            elif step_type == "planner_error":
                st.markdown("### ❌ Planner error")
                st.error(payload.get("error"))
                st.write(payload.get("fallback_answer"))

            elif step_type == "loop_limit":
                st.markdown("### ⚠️ Loop limit reached")
                st.warning(payload.get("fallback_answer"))

            else:
                st.json(payload)

    render_json_expander("Full workflow trace (debug)", decision_trace)


def render_assistant_message(msg: dict) -> None:
    render_markdown_with_table(msg["content"])

    response_type = msg.get("response_type")
    if response_type:
        st.write("**Response type:**", response_type)

    if msg.get("decision_trace") is not None:
        with st.expander("How the workflow moved through the system", expanded=True):
            render_dynamic_trace(msg["decision_trace"])

    render_json_expander("Tool results", msg.get("tool_results"))
    render_json_expander("Session state", msg.get("state"))


def render_page(*, provider: str, temperature: float, session_placeholder) -> None:
    st.subheader("Dynamic MCP Lab / LLM-routed MCP")
    st.caption(
        "The LLM decides whether to ask the user, call an MCP tool, or answer directly. "
        "Python validates and executes the chosen action."
    )

    col1, col2 = st.columns([1, 1])

    with col1:
        render_json_expander("Current session state", st.session_state.travel_state.to_dict())

    with col2:
        with st.expander("What this lab shows", expanded=False):
            st.markdown(
                """
- raw input text
- extracted structured values
- planner prompt sent to the LLM
- raw planner response
- parsed planner decision
- required inputs vs available inputs
- whether the app asked the user or executed a tool
- tool execution result
- final answer
"""
            )

    for msg in st.session_state.messages_dynamic:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                render_assistant_message(msg)
            else:
                st.markdown(msg["content"])

    user_input = st.chat_input("Try dynamic MCP planning...", key="chat_input_dynamic")

    if not user_input:
        return

    st.session_state.messages_dynamic.append(
        {"role": "user", "content": user_input}
    )

    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking dynamically..."):
            result = asyncio.run(
                answer_user_dynamic(
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
                "response_type": result.get("response_type"),
                "decision_trace": result.get("decision_trace"),
                "tool_results": result.get("tool_results"),
                "state": result.get("state"),
            }

            render_assistant_message(assistant_message)

    st.session_state.messages_dynamic.append(assistant_message)