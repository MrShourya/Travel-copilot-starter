import uuid

import streamlit as st

from app.chat.session_state import TravelSessionState


def ensure_ui_state() -> None:
    if "travel_session_id" not in st.session_state:
        st.session_state.travel_session_id = f"travel-{uuid.uuid4().hex[:12]}"

    if "travel_user_id" not in st.session_state:
        st.session_state.travel_user_id = "local-user"

    if "travel_state" not in st.session_state:
        st.session_state.travel_state = TravelSessionState(
            session_id=st.session_state.travel_session_id,
            user_id=st.session_state.travel_user_id,
        )

    if "messages_deterministic" not in st.session_state:
        st.session_state.messages_deterministic = []

    if "messages_dynamic" not in st.session_state:
        st.session_state.messages_dynamic = []