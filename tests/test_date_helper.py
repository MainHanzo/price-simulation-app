from datetime import datetime

from zoneinfo import ZoneInfo

from app.date_helper import market_open_dt, minutes_since_start


def test_market_open_dt_and_minutes_since_start():
    sim_dt = datetime(2024, 1, 2, 11, 45, tzinfo=ZoneInfo("America/New_York"))
    open_dt = market_open_dt(sim_dt)
    assert open_dt.hour == 9 and open_dt.minute == 30
    minutes = minutes_since_start(sim_dt, open_dt)
    assert minutes == 135
