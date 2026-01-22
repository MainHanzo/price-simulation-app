from zoneinfo import ZoneInfo
from datetime import datetime, time

def market_open_dt() -> datetime:
    tz = ZoneInfo("America/New_York")
    now = datetime.now(tz=tz)
    return datetime.combine(now.date(), time(9, 30), tzinfo=tz)

def minutes_since_start(session_start_dt: datetime, open_dt: datetime) -> int:
    return int((session_start_dt - open_dt).total_seconds() // 60)