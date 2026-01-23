import asyncio
import math
import random
from datetime import datetime, time, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo
from app.date_helper import *



CACHE_MAX_SIZE = 390 # number of minutes in a standard trading day

@dataclass
class PricePoint:
    ts: float
    price: float


class PriceEngine:
    def __init__(self, tickers: List[str], simulation_dt: datetime = None) -> None:
        self.tickers = tickers
        self.ticker_latest_cache: Dict[str, PricePoint] = {}
        self.ticker_history_map: Dict[str, List[Optional[PricePoint]]] = {}
        self.ticker_params_map: Dict[str, Dict[str, float]] = {}
        self.lock = asyncio.Lock()
        self.minute_index = 0
        self.simulation_dt = simulation_dt.replace(second=0, microsecond=0)
        self.market_open_dt = market_open_dt(self.simulation_dt)
        nb_minutes = minutes_since_start(self.simulation_dt, self.market_open_dt)

        for t in tickers:
            vol = random.uniform(0.1, 1)
            drift = random.uniform(0.05, 0.9)
            start_price = random.uniform(80.0, 150.0)
            start_point = PricePoint(ts=self.market_open_dt.timestamp(), price=start_price)
            history = [None] * CACHE_MAX_SIZE
            history[0] = start_point
            last_point = start_point
            
            # construct historical prices up to current minute
            for idx in range(1, nb_minutes + 1):
                datetime_incremented = self.market_open_dt + timedelta(minutes=idx)
                next_price = self._next_price(last_point.price, vol, drift)
                last_point = PricePoint(ts=datetime_incremented.timestamp(), price=next_price)
                history[idx] = last_point

            self.ticker_latest_cache[t] = last_point
            self.ticker_history_map[t] = history
            self.ticker_params_map[t] = {"volatility": vol, "drift": drift}
        self.minute_index = nb_minutes + 1
        print(self.minute_index)

    async def step(self) -> None:
        async with self.lock:
            if self.minute_index >= CACHE_MAX_SIZE:
                return
            print(self.minute_index)
            idx = self.minute_index
            datetime_incremented = self.market_open_dt + timedelta(minutes=idx)
            for t in self.tickers:
                last = self.ticker_latest_cache[t]
                vol = self.ticker_params_map[t]["volatility"]
                drift = self.ticker_params_map[t]["drift"]
                next_price = self._next_price(last.price, vol, drift)
                point = PricePoint(ts=datetime_incremented.timestamp(), price=next_price)
                self.ticker_latest_cache[t] = point
                self.ticker_history_map[t][idx] = point
            self.minute_index += 1

    @staticmethod
    def _next_price(last_price: float, vol: float, drift: float) -> float:
        dt = 1.0 / CACHE_MAX_SIZE  # one minute of a 6.5h trading day
        z = random.gauss(0.0, 1.0)
        return last_price * math.exp((drift - 0.5 * vol * vol) * dt + vol * math.sqrt(dt) * z)
