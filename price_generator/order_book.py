"""Aggregated liquidity for the active anonymous synthetic-price run."""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import random
import time
from typing import Any


class SimulatedOrderBook:
    def __init__(self, run_id: int) -> None:
        self.run_id = run_id
        self._random = random.Random()
        self._snapshot: dict[str, Any] | None = None
        self._quantity_updated: float | None = None

    def update(self, price: float, simulated_seconds: float, running: bool) -> dict[str, Any]:
        previous = self._snapshot
        now = time.monotonic()
        status = "running" if running else "stopped"
        change_quantities = previous is None or (running and self._quantity_updated is not None and now - self._quantity_updated >= 1)
        if previous and not change_quantities and previous["reference_price"] == price and previous["reference_simulated_seconds"] == simulated_seconds and previous["status"] == status:
            return previous

        reference = Decimal(str(price))
        # Keep ten positive levels even when a long synthetic run falls below
        # a cent. Ordinary stock/crypto profile prices retain a one-cent grid.
        tick = min(Decimal("0.01"), Decimal(10) ** (reference.adjusted() - 2))
        units = reference / tick
        bid = int(units.to_integral_value(rounding=ROUND_CEILING)) - 1
        ask = int(units.to_integral_value(rounding=ROUND_FLOOR)) + 1

        def levels(side: str, best: int, direction: int) -> list[dict[str, int | float]]:
            rows = []
            cumulative = 0
            for index in range(10):
                if previous is None:
                    quantity = self._random.randint(50, 500)
                else:
                    quantity = previous[side][index]["quantity"]
                    if change_quantities:
                        changed = max(1, quantity + self._random.choice((-25, -10, 10, 25)))
                        quantity = changed if changed != quantity else quantity + 1
                cumulative += quantity
                rows.append({"price": float((best + direction * index) * tick), "quantity": quantity, "cumulative_quantity": cumulative})
            return rows

        self._snapshot = {
            "run_id": self.run_id,
            "sequence": previous["sequence"] + 1 if previous else 1,
            "ts": time.time(),
            "reference_price": price,
            "reference_simulated_seconds": simulated_seconds,
            "status": status,
            "tick_size": float(tick),
            "bids": levels("bids", bid, -1),
            "asks": levels("asks", ask, 1),
        }
        if change_quantities:
            self._quantity_updated = now
        return self._snapshot
