from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class TravelSessionState:
    session_id: str
    user_id: str
    trip_days: Optional[int] = None
    date_text: Optional[str] = None
    city: Optional[str] = None
    budget_amount: Optional[float] = None
    budget_currency: Optional[str] = None
    target_currency: Optional[str] = None
    last_user_message: Optional[str] = None
    flow_stage: str = "collecting"

    def to_dict(self) -> dict:
        return asdict(self)