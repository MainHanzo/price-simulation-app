import asyncio
import math
import random
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo
from app.date_helper import market_open_dt, minutes_since_start



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
        self.ticker_requested: set[str] = set()
        self.lock = asyncio.Lock()
        self.minute_index = 0
        if simulation_dt is None:
            simulation_dt = datetime(2024, 1, 2, 11, 30, tzinfo=ZoneInfo("America/New_York"))
        elif simulation_dt.tzinfo is None:
            simulation_dt = simulation_dt.replace(tzinfo=ZoneInfo("America/New_York"))
        self.simulation_dt = simulation_dt.replace(second=0, microsecond=0)
        self.market_open_dt = market_open_dt(self.simulation_dt)

        for t in tickers:
            vol = random.uniform(0.1, 1)
            drift = random.uniform(0.05, 0.9)
            self.ticker_params_map[t] = {"volatility": vol, "drift": drift}


    async def step(self, simulation_cur_dt: datetime | None = None) -> None:
        async with self.lock:
            idx = self.minute_index if simulation_cur_dt is None else minutes_since_start(simulation_cur_dt, self.market_open_dt)
            if idx < 0 or idx >= CACHE_MAX_SIZE:
                return
            for t in self.ticker_requested:
                if t not in self.ticker_latest_cache:
                    self._generate_history_for_ticker(t, simulation_cur_dt or self.simulation_dt)
                for minute in range(idx + 1):
                    point_dt = self.market_open_dt + timedelta(minutes=minute)
                    last = self.ticker_latest_cache[t]
                    if last.ts >= point_dt.timestamp():
                        continue
                    params = self.ticker_params_map[t]
                    next_price = self._next_price(last.price, params["volatility"], params["drift"])
                    point = PricePoint(ts=point_dt.timestamp(), price=next_price)
                    logging.info("Generated price for %s at %s: %.2f", t, point_dt.isoformat(), next_price)
                    self.ticker_latest_cache[t] = point
                    self.ticker_history_map[t][minute] = point
            self.minute_index = max(self.minute_index, idx + 1)

    @staticmethod
    def _next_price(last_price: float, vol: float, drift: float) -> float:
        dt = 1.0 / CACHE_MAX_SIZE  # one minute of a 6.5h trading day
        z = random.gauss(0.0, 1.0)
        return max(0.11, last_price * math.exp((drift - 0.5 * vol * vol) * dt + vol * math.sqrt(dt) * z))
    
    def _generate_history_for_ticker(self, ticker: str, simulation_cur_dt: datetime) -> None:
        if simulation_cur_dt.tzinfo is None:
            simulation_cur_dt = simulation_cur_dt.replace(tzinfo=ZoneInfo("America/New_York"))
        nb_minutes = max(0, min(CACHE_MAX_SIZE - 1, minutes_since_start(simulation_cur_dt, self.market_open_dt)))

        start_price = random.uniform(80.0, 150.0)
        start_point = PricePoint(ts=min(self.market_open_dt, simulation_cur_dt.replace(second=0, microsecond=0)).timestamp(), price=start_price)
        history = [None] * CACHE_MAX_SIZE
        history[0] = start_point
        last_point = start_point
        
        # construct historical prices up to current minute
        for idx in range(1, nb_minutes + 1):
            datetime_incremented = self.market_open_dt + timedelta(minutes=idx)
            next_price = self._next_price(last_point.price, self.ticker_params_map[ticker]["volatility"], self.ticker_params_map[ticker]["drift"])
            last_point = PricePoint(ts=datetime_incremented.timestamp(), price=next_price)
            history[idx] = last_point

        self.ticker_latest_cache[ticker] = last_point
        self.ticker_history_map[ticker] = history
        self.minute_index = max(self.minute_index, nb_minutes + 1)
        return
    
