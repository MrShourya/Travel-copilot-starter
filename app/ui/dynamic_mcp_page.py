import asyncio

import streamlit as st

from app.chat.dynamic_mcp.agent import answer_user_dynamic
from app.chat.session_state import TravelSessionState
from app.ui.rendering_common import render_json_expander, render_markdown_with_table


STATIC_STAGE_COLORS = {
    "user_input": "#F8BBD0",          # pink
    "input_understanding": "#E1BEE7", # purple
    "state_extraction": "#D1C4E9",    # deeper purple
    "live_tool_catalog": "#C5CAE9",   # lavender-blue
    "tool_execution": "#FFE0B2",      # orange
    "final_output": "#CFD8DC",        # grey
    "planner_loop": "#ECEFF1",        # neutral
}

LOOP_STEP_COLORS = {
    1: "#E3F2FD",  # light blue
    2: "#BBDEFB",
    3: "#90CAF9",
    4: "#64B5F6",
    5: "#42A5F5",
}


def _render_stage_box(label: str, color: str, subtitle: str = "") -> None:
    st.markdown(
        f"""
<div style="
    background:{color};
    border:1px solid rgba(0,0,0,0.10);
    border-radius:14px;
    padding:14px 12px;
    min-height:90px;
    text-align:center;
    color:#111;">
    <div style="font-size:16px; font-weight:700;">{label}</div>
    <div style="font-size:12px; margin-top:6px; opacity:0.8;">{subtitle}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def _loop_color(loop_index: int | None) -> str:
    if loop_index in LOOP_STEP_COLORS:
        return LOOP_STEP_COLORS[loop_index]
    return "#ECEFF1"


def _step_icon(label: str) -> str:
    if label in {
        "User Input",
        "Input Understanding",
        "State Extraction",
        "Live Tool Catalog",
        "Planner Prompt",
        "Planner Response",
        "Missing-Field Prompt",
        "Missing-Field Response",
        "Final Answer Prompt",
        "Final Answer Response",
    }:
        return "🟢"
    if "Failed" in label or "Error" in label:
        return "🔴"
    return "🟡"


def _build_step_sequence(decision_trace: list[dict]) -> list[dict]:
    sequence = []

    for step in decision_trace:
        step_type = step.get("step_type")
        loop_index = step.get("loop_index")
        payload = step.get("payload", {})

        if step_type == "turn_start":
            sequence.append({
                "label": "User Input",
                "step_type": step_type,
                "loop_index": None,
                "color": STATIC_STAGE_COLORS["user_input"],
                "payload": payload,
            })

        elif step_type == "input_understanding":
            sequence.append({
                "label": "Input Understanding",
                "step_type": step_type,
                "loop_index": None,
                "color": STATIC_STAGE_COLORS["input_understanding"],
                "payload": payload,
            })

        elif step_type == "state_extraction":
            sequence.append({
                "label": "State Extraction",
                "step_type": step_type,
                "loop_index": None,
                "color": STATIC_STAGE_COLORS["state_extraction"],
                "payload": payload,
            })

        elif step_type == "live_tool_catalog":
            sequence.append({
                "label": "Live Tool Catalog",
                "step_type": step_type,
                "loop_index": None,
                "color": STATIC_STAGE_COLORS["live_tool_catalog"],
                "payload": payload,
            })

        elif step_type == "planner_prompt":
            sequence.append({
                "label": "Planner Prompt",
                "step_type": step_type,
                "loop_index": loop_index,
                "color": _loop_color(loop_index),
                "payload": payload,
            })

        elif step_type == "planner_response":
            sequence.append({
                "label": "Planner Response",
                "step_type": step_type,
                "loop_index": loop_index,
                "color": _loop_color(loop_index),
                "payload": payload,
            })

        elif step_type == "input_requirements_check":
            sequence.append({
                "label": "Input Requirements Check",
                "step_type": step_type,
                "loop_index": loop_index,
                "color": _loop_color(loop_index),
                "payload": payload,
            })

        elif step_type == "validation_result":
            sequence.append({
                "label": "Validation Result",
                "step_type": step_type,
                "loop_index": loop_index,
                "color": _loop_color(loop_index),
                "payload": payload,
            })

        elif step_type == "missing_field_prompt":
            sequence.append({
                "label": "Missing-Field Prompt",
                "step_type": step_type,
                "loop_index": loop_index,
                "color": _loop_color(loop_index),
                "payload": payload,
            })

        elif step_type == "missing_field_response":
            sequence.append({
                "label": "Missing-Field Response",
                "step_type": step_type,
                "loop_index": loop_index,
                "color": _loop_color(loop_index),
                "payload": payload,
            })

        elif step_type == "action_decision":
            sequence.append({
                "label": "Action Decision",
                "step_type": step_type,
                "loop_index": loop_index,
                "color": _loop_color(loop_index),
                "payload": payload,
            })

        elif step_type in {"tool_execution", "tool_execution_failed"}:
            tool_name = (
                payload.get("tool_name")
                or payload.get("execution", {}).get("tool_name")
                or "unknown_tool"
            )
            label = f"Tool Execution: {tool_name}" if step_type == "tool_execution" else f"Tool Execution Failed: {tool_name}"
            sequence.append({
                "label": label,
                "step_type": step_type,
                "loop_index": None,
                "color": STATIC_STAGE_COLORS["tool_execution"],
                "payload": payload,
            })

        elif step_type == "final_answer_prompt":
            sequence.append({
                "label": "Final Answer Prompt",
                "step_type": step_type,
                "loop_index": None,
                "color": STATIC_STAGE_COLORS["final_output"],
                "payload": payload,
            })

        elif step_type == "final_answer_response":
            sequence.append({
                "label": "Final Answer Response",
                "step_type": step_type,
                "loop_index": None,
                "color": STATIC_STAGE_COLORS["final_output"],
                "payload": payload,
            })

        elif step_type in {"final_output", "planner_error", "loop_limit"}:
            label = "Final Output"
            if step_type == "planner_error":
                label = "Final Output Error"
            elif step_type == "loop_limit":
                label = "Final Output Loop Limit"
            sequence.append({
                "label": label,
                "step_type": step_type,
                "loop_index": None,
                "color": STATIC_STAGE_COLORS["final_output"],
                "payload": payload,
            })

    return sequence


def _render_step_header(step: dict, idx: int) -> None:
    label = step["label"]
    loop_index = step.get("loop_index")
    color = step["color"]

    subtitle = f"Loop {loop_index}" if loop_index else "Static step"
    icon = _step_icon(label)

    st.markdown(
        f"""
<div style="
    background:{color};
    padding:12px;
    border-radius:10px;
    margin-bottom:12px;
    color:#111;
    border:1px solid rgba(0,0,0,0.08);">
    <div style="font-weight:700;">{icon} {idx}. {label}</div>
    <div style="font-size:12px; opacity:0.8;">{subtitle}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_dynamic_trace(decision_trace: list[dict] | None, trace_key_prefix: str = "") -> None:
    if not decision_trace:
        st.info("No workflow trace available for this turn.")
        return

    sequence = _build_step_sequence(decision_trace)

    executed_tool_steps = [s for s in sequence if s["label"].startswith("Tool Execution:")]
    final_steps = [s for s in sequence if s["label"].startswith("Final Output")]
    planner_loop_count = len(set(s["loop_index"] for s in sequence if s.get("loop_index")))

    st.markdown("## 🧭 Workflow Movement")

    top_cols = st.columns(5)
    with top_cols[0]:
        _render_stage_box("1. User Input", STATIC_STAGE_COLORS["user_input"], "Runs once")
    with top_cols[1]:
        _render_stage_box("2. Extraction", STATIC_STAGE_COLORS["state_extraction"], "Runs once")
    with top_cols[2]:
        _render_stage_box("3. Planner Loop", STATIC_STAGE_COLORS["planner_loop"], f"Repeated {planner_loop_count} time(s)")
    with top_cols[3]:
        _render_stage_box("4. Tool Execution", STATIC_STAGE_COLORS["tool_execution"], f"{len(executed_tool_steps)} step(s)")
    with top_cols[4]:
        _render_stage_box("5. Final Output", STATIC_STAGE_COLORS["final_output"], f"{len(final_steps)} step(s)")

    tab_labels = [f"{_step_icon(step['label'])} {idx}. {step['label']}" for idx, step in enumerate(sequence, start=1)]
    tabs = st.tabs(tab_labels)

    for idx, (tab, step) in enumerate(zip(tabs, sequence), start=1):
        with tab:
            _render_step_header(step, idx)

            step_type = step["step_type"]
            payload = step["payload"]

            if step_type == "turn_start":
                st.write("**Raw user text:**")
                st.info(payload.get("user_query", ""))
                st.write("**Model provider:**", payload.get("provider"))
                st.write("**Flow stage before this turn:**", payload.get("flow_stage_before"))
                render_json_expander("State before turn", payload.get("state_before"))

            elif step_type == "input_understanding":
                analysis = payload.get("input_analysis", {})
                st.write("**Normalized text:**", analysis.get("normalized_text"))
                render_json_expander("Detected intent hints", analysis.get("keyword_hints"), expanded=True)

            elif step_type == "state_extraction":
                st.write("**Extracted slots:**")
                st.json(payload.get("extracted_slots", {}))
                st.write("**Flow stage after parse:**", payload.get("flow_stage_after_parse"))
                render_json_expander("Full state after extraction", payload.get("state_after"))

            elif step_type == "live_tool_catalog":
                render_json_expander("Available live tools", payload.get("available_tools", []), expanded=False)

            elif step_type == "planner_prompt":
                st.text_area(
                    f"Rendered prompt {idx}",
                    value=payload.get("prompt_text", ""),
                    height=280,
                    disabled=True,
                    key=f"planner_prompt_{trace_key_prefix}_{idx}",
                )

            elif step_type == "planner_response":
                st.write("**Raw LLM response:**")
                st.code(payload.get("raw_response", ""), language="json")
                st.write("**Parsed decision:**")
                st.json(payload.get("parsed_decision", {}))

            elif step_type == "input_requirements_check":
                explanation = payload.get("validation_explanation", {})
                st.write("**Selected action/tool:**", explanation.get("tool_name"))
                st.write("**Required inputs:**", explanation.get("required_args"))
                st.write("**Provided inputs:**")
                st.json(explanation.get("provided_args", {}))
                st.write("**Missing inputs:**", explanation.get("missing_args"))

            elif step_type == "validation_result":
                st.write("**Validation result:**")
                st.json(payload.get("validation", {}))

            elif step_type == "missing_field_prompt":
                st.text_area(
                    f"Missing-field prompt {idx}",
                    value=payload.get("prompt_text", ""),
                    height=220,
                    disabled=True,
                    key=f"missing_field_prompt_{trace_key_prefix}_{idx}",
                )

            elif step_type == "missing_field_response":
                st.write("**Raw LLM response for missing-field question:**")
                st.code(payload.get("raw_response", ""), language="text")
                st.write("**Generated question:**")
                st.info(payload.get("question"))

            elif step_type == "action_decision":
                action = payload.get("action")
                st.write("**Chosen action:**", action)
                st.write("**Reason:**", payload.get("reason"))

                if action == "call_tool":
                    st.write("**Tool chosen:**", payload.get("tool_name"))
                    st.write("**MCP family:**", payload.get("mcp_family"))
                    render_json_expander("Arguments", payload.get("arguments"), expanded=True)
                    render_json_expander(
                        "Where each argument came from",
                        payload.get("argument_provenance"),
                        expanded=True,
                    )

                elif action == "ask_user":
                    st.write("**Missing fields:**", payload.get("missing_fields"))
                    st.info(payload.get("question"))

                elif action == "answer":
                    st.write("**Planner draft answer:**")
                    st.info(payload.get("planner_draft_answer"))

            elif step_type == "tool_execution":
                st.json(payload.get("execution", {}))

            elif step_type == "tool_execution_failed":
                st.error(payload.get("fallback_answer"))

            elif step_type == "final_answer_prompt":
                st.text_area(
                    f"Final answer prompt {idx}",
                    value=payload.get("prompt_text", ""),
                    height=280,
                    disabled=True,
                    key=f"final_answer_prompt_{trace_key_prefix}_{idx}",
                )

            elif step_type == "final_answer_response":
                st.write("**Raw LLM response for final answer:**")
                st.code(payload.get("raw_response", ""), language="text")
                st.write("**Generated final answer:**")
                st.success(payload.get("answer"))

            elif step_type == "final_output":
                response_type = payload.get("response_type")
                st.write("**Response type:**", response_type)
                if response_type == "question":
                    st.info(payload.get("answer"))
                else:
                    st.success(payload.get("answer"))

            elif step_type == "planner_error":
                st.error(payload.get("error"))
                st.write(payload.get("fallback_answer"))

            elif step_type == "loop_limit":
                st.warning(payload.get("fallback_answer"))

    render_json_expander("Full workflow trace (debug)", decision_trace)


def render_assistant_message(msg: dict) -> None:
    render_markdown_with_table(msg["content"])

    response_type = msg.get("response_type")
    if response_type:
        st.write("**Response type:**", response_type)

    if msg.get("decision_trace") is not None:
        with st.expander("How the workflow moved through the system", expanded=False):
            trace_key_prefix = str(msg.get("message_id", "dynamic_msg"))
            render_dynamic_trace(msg["decision_trace"], trace_key_prefix=trace_key_prefix)

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
Static stages:
- User Input
- Input Understanding
- State Extraction
- Live Tool Catalog
- Tool Execution
- Final Answer Prompt
- Final Answer Response
- Final Output

Repeated loop stages:
- Planner Prompt
- Planner Response
- Input Requirements Check
- Validation Result
- Missing-Field Prompt
- Missing-Field Response
- Action Decision
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
                "message_id": f"dynamic_{len(st.session_state.messages_dynamic)}",
                "role": "assistant",
                "content": result["answer"],
                "response_type": result.get("response_type"),
                "decision_trace": result.get("decision_trace"),
                "tool_results": result.get("tool_results"),
                "state": result.get("state"),
            }

            render_assistant_message(assistant_message)

    st.session_state.messages_dynamic.append(assistant_message)