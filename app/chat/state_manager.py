import re
from datetime import datetime, timedelta

from app.chat.session_state import TravelSessionState
from app.chat.tool_router import (
    extract_amount_and_currency,
    extract_city,
    extract_target_currency,
    extract_trip_days,
)


def extract_explicit_date(user_query: str) -> str | None:
    match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", user_query)
    if not match:
        return None

    candidate = match.group(1)
    try:
        datetime.strptime(candidate, "%Y-%m-%d")
        return candidate
    except ValueError:
        return None


def infer_date_text(user_query: str) -> str | None:
    q = user_query.lower()

    explicit_date = extract_explicit_date(user_query)
    if explicit_date:
        return explicit_date

    if "next week" in q:
        return "next week"
    if "tomorrow" in q:
        return "tomorrow"
    if "weekend" in q:
        return "this weekend"

    return None


def derive_start_end_dates(date_text: str | None, trip_days: int | None) -> tuple[str | None, str | None]:
    if not date_text:
        return None, None

    try:
        start_dt = datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError:
        return None, None

    start_date = start_dt.isoformat()
    end_date = None

    if trip_days and trip_days > 0:
        end_dt = start_dt + timedelta(days=trip_days - 1)
        end_date = end_dt.isoformat()

    return start_date, end_date


def update_state_from_user_query(
    current_state: TravelSessionState,
    user_query: str,
) -> TravelSessionState:
    query_lower = user_query.lower()

    city = extract_city(user_query)
    days = extract_trip_days(user_query)
    date_text = infer_date_text(user_query)

    amount, source_currency = extract_amount_and_currency(user_query)
    target_currency = extract_target_currency(user_query)

    if city != "Unknown":
        current_state.city = city

    if re.search(r"\b\d+\s*[- ]?day", query_lower):
        current_state.trip_days = days

    if date_text:
        current_state.date_text = date_text

    start_date, end_date = derive_start_end_dates(
        current_state.date_text,
        current_state.trip_days,
    )
    if start_date:
        current_state.start_date = start_date
    if end_date:
        current_state.end_date = end_date

    if any(token in query_lower for token in ["under", "budget", "usd", "eur", "inr", "aed"]):
        current_state.budget_amount = amount
        current_state.budget_currency = source_currency

    if target_currency:
        current_state.target_currency = target_currency

    current_state.last_user_message = user_query
    current_state.flow_stage = determine_flow_stage(current_state)

    return current_state


def determine_flow_stage(state: TravelSessionState) -> str:
    if not state.city:
        return "choose_place"

    has_dates = bool(state.date_text or state.start_date)

    if not state.trip_days or not has_dates:
        return "choose_dates"

    return "show_itinerary"