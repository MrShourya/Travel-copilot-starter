from app.chat.session_state import TravelSessionState
from app.chat.tool_router import (
    extract_amount_and_currency,
    extract_city,
    extract_target_currency,
    extract_trip_days,
)


def infer_date_text(user_query: str) -> str | None:
    q = user_query.lower()
    if "next week" in q:
        return "next week"
    if "tomorrow" in q:
        return "tomorrow"
    if "weekend" in q:
        return "this weekend"
    return None


def update_state_from_user_query(
    current_state: TravelSessionState,
    user_query: str,
) -> TravelSessionState:
    city = extract_city(user_query)
    days = extract_trip_days(user_query)
    date_text = infer_date_text(user_query)

    amount, source_currency = extract_amount_and_currency(user_query)
    target_currency = extract_target_currency(user_query)

    if city != "Unknown":
        current_state.city = city

    # only update days if explicitly present
    if "day" in user_query.lower():
        current_state.trip_days = days

    if date_text:
        current_state.date_text = date_text

    # only update budget if amount/currency language is present
    if any(token in user_query.lower() for token in ["under", "budget", "usd", "eur", "inr"]):
        current_state.budget_amount = amount
        current_state.budget_currency = source_currency

    if target_currency:
        current_state.target_currency = target_currency

    current_state.last_user_message = user_query
    current_state.flow_stage = determine_flow_stage(current_state)

    return current_state


def determine_flow_stage(state: TravelSessionState) -> str:
    if not state.trip_days or not state.date_text:
        return "choose_dates"
    if not state.city:
        return "choose_place"
    return "show_itinerary"