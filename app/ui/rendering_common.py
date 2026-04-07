import streamlit as st

from app.ui.rendering import extract_first_markdown_table


def render_markdown_with_table(content: str) -> None:
    table_df = extract_first_markdown_table(content)
    if table_df is not None:
        st.table(table_df)
    st.markdown(content)


def render_json_expander(title: str, payload, expanded: bool = False) -> None:
    if payload is None:
        return
    with st.expander(title, expanded=expanded):
        st.json(payload)