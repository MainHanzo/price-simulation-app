import asyncio
import math
import random
import logging
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
        self.ticker_requested: set[str] = set()
        self.lock = asyncio.Lock()
        self.minute_index = 0
        self.simulation_dt = simulation_dt.replace(second=0, microsecond=0)
        self.market_open_dt = market_open_dt(self.simulation_dt)

        for t in tickers:
            vol = random.uniform(0.1, 1)
            drift = random.uniform(0.05, 0.9)
            self.ticker_params_map[t] = {"volatility": vol, "drift": drift}


    async def step(self) -> List[dict]:
        async with self.lock:
            updates: List[dict] = []
            if self.minute_index >= CACHE_MAX_SIZE:
                return updates
            print(self.minute_index)
            idx = self.minute_index
            datetime_incremented = self.market_open_dt + timedelta(minutes=idx)
            for t in self.ticker_requested:
                if t not in self.ticker_latest_cache:
                    self._generate_history_for_ticker(t, self.simulation_dt)
                    if t not in self.ticker_latest_cache:
                        continue
                last = self.ticker_latest_cache[t]
                vol = self.ticker_params_map[t]["volatility"]
                drift = self.ticker_params_map[t]["drift"]
                next_price = self._next_price(last.price, vol, drift)
                point = PricePoint(ts=datetime_incremented.timestamp(), price=next_price)
                logging.info("Generated price for %s at %s: %.2f", t, datetime_incremented.isoformat(), next_price)
                self.ticker_latest_cache[t] = point
                self.ticker_history_map[t][idx] = point
                updates.append({"ticker": t, "ts": point.ts, "price": point.price})
            self.minute_index += 1
            return updates

    @staticmethod
    def _next_price(last_price: float, vol: float, drift: float) -> float:
        dt = 1.0 / CACHE_MAX_SIZE  # one minute of a 6.5h trading day
        z = random.gauss(0.0, 1.0)
        return last_price * math.exp((drift - 0.5 * vol * vol) * dt + vol * math.sqrt(dt) * z)
    
    def _generate_history_for_ticker(self, ticker: str, simulation_cur_dt: datetime) -> None:
        nb_minutes = minutes_since_start(simulation_cur_dt, self.market_open_dt)
        if nb_minutes >= 390:
            nb_minutes = 389
        print(nb_minutes)

        start_price = random.uniform(80.0, 150.0)
        start_point = PricePoint(ts=self.market_open_dt.timestamp(), price=start_price)
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
        self.minute_index = nb_minutes + 1
        return
    
