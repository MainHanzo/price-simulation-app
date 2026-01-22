import asyncio
import math
import random
from datetime import datetime, time as dt_time, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo


@dataclass
class PricePoint:
    ts: float
    price: float


class PriceEngine:
    def __init__(self, tickers: List[str], session_start_dt: Optional[datetime] = None) -> None:
        self.tickers = tickers
        self.latest: Dict[str, PricePoint] = {}
        self.history: Dict[str, List[Optional[PricePoint]]] = {}
        self.params: Dict[str, Dict[str, float]] = {}
        self.lock = asyncio.Lock()
        self.minute_index = 0
        if session_start_dt is None:
            self.session_start_dt = self._market_open_dt()
        else:
            self.session_start_dt = session_start_dt
        minutes_since_start = self._minutes_since_start(self.session_start_dt, self._market_open_dt())

        for t in tickers:
            vol = 0.2
            drift = 0.05
            start_price = random.uniform(80.0, 150.0)
            start_point = PricePoint(ts=self.session_start_dt.timestamp(), price=start_price)
            history = [None] * 390
            history[0] = start_point

            last_point = start_point
            print(minutes_since_start)

            for idx in range(1, minutes_since_start + 1):
                session_time = self.session_start_dt + timedelta(minutes=idx)
                next_price = self._next_price(last_point.price, vol, drift)
                last_point = PricePoint(ts=session_time.timestamp(), price=next_price)
                history[idx] = last_point

            self.latest[t] = last_point
            self.history[t] = history
            self.params[t] = {"volatility": vol, "drift": drift}
        self.minute_index = minutes_since_start + 1

    async def step(self) -> None:
        async with self.lock:
            idx = self.minute_index
            session_time = self.session_start_dt + timedelta(minutes=idx)
            for t in self.tickers:
                last = self.latest[t]
                vol = self.params[t]["volatility"]
                drift = self.params[t]["drift"]
                next_price = self._next_price(last.price, vol, drift)
                point = PricePoint(ts=session_time.timestamp(), price=next_price)
                self.latest[t] = point
                self.history[t][idx] = point
            self.minute_index = (self.minute_index + 1) % 390
            if self.minute_index == 0:
                self.session_start_dt = self.session_start_dt + timedelta(days=1)

    @staticmethod
    def _minutes_since_start(session_start_dt: datetime, open_dt: datetime) -> int:
        return int((session_start_dt - open_dt).total_seconds() // 60)

    @staticmethod
    def _next_price(last_price: float, vol: float, drift: float) -> float:
        dt = 1.0 / 390.0  # one minute of a 6.5h trading day
        z = random.gauss(0.0, 1.0)
        return last_price * math.exp((drift - 0.5 * vol * vol) * dt + vol * math.sqrt(dt) * z)

    @staticmethod
    def _session_start_dt() -> datetime:
        tz = ZoneInfo("America/New_York")
        now = datetime.now(tz=tz)
        return datetime.combine(now.date(), dt_time(9, 30), tzinfo=tz)


    @staticmethod
    def _market_open_dt() -> datetime:
        tz = ZoneInfo("America/New_York")
        now = datetime.now(tz=tz)
        return datetime.combine(now.date(), dt_time(9, 30), tzinfo=tz)