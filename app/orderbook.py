"""Shared aggregated simulated liquidity; consumers receive complete snapshots."""

import math
import random
from dataclasses import asdict, dataclass
from datetime import datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")


def is_session_open(now: datetime) -> bool:
    return time(9, 30) <= now.astimezone(NEW_YORK).time() < time(16)


@dataclass(frozen=True)
class BookLevel:
    price: float
    quantity: int
    cumulative_quantity: int


@dataclass(frozen=True)
class BookSnapshot:
    ticker: str
    sequence: int
    ts: float
    reference_price: float
    reference_ts: float
    session_status: str
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]

    def to_dict(self) -> dict:
        return asdict(self)


class OrderBook:
    """One state per ticker. Only the scheduler advances existing books.

    Immutable snapshot replacement is atomic; streams retain no per-client
    queue or history of missed updates.
    """

    def __init__(self, rng: random.Random | None = None) -> None:
        self.snapshots: dict[str, BookSnapshot] = {}
        self.rng = rng or random.Random()

    def update(self, ticker: str, price: float, price_ts: float, now: datetime) -> BookSnapshot:
        previous = self.snapshots.get(ticker)
        status = "open" if is_session_open(now) else "closed"
        if previous and status == "closed" and previous.session_status == "closed":
            return previous

        # Strictly bracket the unrounded engine price on the cent grid.
        cents = Decimal(str(price)) * 100
        best_bid = math.ceil(cents) - 1
        best_ask = math.floor(cents) + 1

        def levels(side: str, best: int, direction: int) -> tuple[BookLevel, ...]:
            old = getattr(previous, side) if previous else ()
            total = 0
            result = []
            for index in range(10):
                if old:
                    quantity = max(1, old[index].quantity + self.rng.choice((-25, -10, 10, 25)))
                    if quantity == old[index].quantity:
                        quantity += 1
                else:
                    quantity = self.rng.randint(50, 500)
                total += quantity
                result.append(BookLevel((best + direction * index) / 100, quantity, total))
            return tuple(result)

        if previous and status == "closed":
            bids, asks = previous.bids, previous.asks
        else:
            bids, asks = levels("bids", best_bid, -1), levels("asks", best_ask, 1)
        snapshot = BookSnapshot(
            ticker=ticker,
            sequence=previous.sequence + 1 if previous else 1,
            ts=now.timestamp(),
            reference_price=price,
            reference_ts=price_ts,
            session_status=status,
            bids=bids,
            asks=asks,
        )
        self.snapshots[ticker] = snapshot
        return snapshot
