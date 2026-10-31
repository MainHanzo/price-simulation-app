"""The observable order-book contract, exercised over real HTTP connections."""

import json
import time
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import httpx
import pytest

from conftest import running_server


def snapshots(response: httpx.Response) -> Iterator[dict[str, Any]]:
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    for line in response.iter_lines():
        if line.startswith("data: "):
            yield json.loads(line[6:])


def assert_book(book: dict[str, Any]) -> None:
    assert book["ticker"] == "AAPL"
    assert book["sequence"] >= 1
    assert book["ts"] >= book["reference_ts"]
    for side, descending in (("bids", True), ("asks", False)):
        levels = book[side]
        assert len(levels) == 10
        prices = [level["price"] for level in levels]
        assert prices == sorted(prices, reverse=descending)
        assert len(set(prices)) == 10
        total = 0
        for level in levels:
            price = Decimal(str(level["price"]))
            assert price > 0 and price * 100 == (price * 100).to_integral_value()
            assert isinstance(level["quantity"], int) and level["quantity"] > 0
            total += level["quantity"]
            assert level["cumulative_quantity"] == total
    assert book["bids"][0]["price"] < book["reference_price"] < book["asks"][0]["price"]


def test_snapshot_initializes_ticker_and_aligns_with_price(market: httpx.Client) -> None:
    response = market.get("/api/orderbook/aapl")
    assert response.status_code == 200
    book = response.json()
    assert_book(book)
    assert book["session_status"] == "open"
    latest = market.get("/api/latest/AAPL").json()
    assert latest == {"ts": book["reference_ts"], "price": book["reference_price"]}
    history = market.get("/api/history/AAPL").json()
    assert history[-1] == latest


@pytest.mark.parametrize("suffix", ["", "/stream"])
def test_unsupported_ticker_returns_404(market: httpx.Client, suffix: str) -> None:
    assert market.get(f"/api/orderbook/UNKNOWN{suffix}").status_code == 404


def test_stream_updates_shared_liquidity_and_reconnects(market: httpx.Client) -> None:
    with market.stream("GET", "/api/orderbook/AAPL/stream") as response:
        events = snapshots(response)
        first = next(events)
        second = next(events)
        assert_book(first)
        assert_book(second)
        assert second["sequence"] > first["sequence"]
        assert second["ts"] > first["ts"]
        assert second["reference_ts"] == first["reference_ts"]
        assert [row["quantity"] for row in second["bids"]] != [row["quantity"] for row in first["bids"]]
        rest = market.get("/api/orderbook/AAPL").json()
        assert rest == second
        with market.stream("GET", "/api/orderbook/AAPL/stream") as other:
            assert next(snapshots(other)) == second
    with market.stream("GET", "/api/orderbook/AAPL/stream", headers={"Last-Event-ID": "999999"}) as response:
        reconnected = next(snapshots(response))
        assert reconnected["sequence"] >= second["sequence"]
        assert_book(reconnected)


@pytest.mark.parametrize("start", ["2024-01-02T09:00:00-05:00", "2024-01-02T16:00:00-05:00"])
def test_closed_book_is_frozen(start: str) -> None:
    with running_server(start) as client:
        first = client.get("/api/orderbook/AAPL").json()
        assert_book(first)
        assert first["session_status"] == "closed"
        time.sleep(1.2)
        assert client.get("/api/orderbook/AAPL").json() == first


def test_startup_without_simulation_configuration() -> None:
    with running_server(None) as client:
        assert client.get("/api/config").json()["simulation_start_iso"] == "2024-01-02T11:30:00-05:00"
        assert client.get("/api/orderbook/AAPL").status_code == 200


def test_session_uses_new_york_time_for_utc_configuration() -> None:
    with running_server("2024-01-02T16:30:00+00:00") as client:
        config = client.get("/api/config").json()
        assert config["simulation_start_iso"] == "2024-01-02T11:30:00-05:00"
        book = client.get("/api/orderbook/AAPL").json()
        assert book["session_status"] == "open"
        assert_book(book)


@pytest.mark.parametrize(
    ("start", "status"),
    [("2024-01-02T09:29:59-05:00", "open"), ("2024-01-02T15:59:59-05:00", "closed")],
)
def test_session_boundary_transitions(start: str, status: str) -> None:
    with running_server(start) as client:
        client.get("/api/orderbook/AAPL")
        time.sleep(1.3)
        book = client.get("/api/orderbook/AAPL").json()
        assert book["session_status"] == status
        assert_book(book)


def test_price_boundary_and_second_ticker_do_not_rewind_clock() -> None:
    with running_server("2024-01-02T11:30:59-05:00") as client:
        initial = client.get("/api/orderbook/AAPL").json()
        time.sleep(1.3)
        updated = client.get("/api/orderbook/AAPL").json()
        assert updated["reference_ts"] > initial["reference_ts"]
        assert_book(updated)
        before = client.get("/api/config").json()["simulation_cur_dt_ts"]
        client.get("/api/orderbook/MSFT")
        assert client.get("/api/latest/AAPL").json()["ts"] == updated["reference_ts"]
        assert client.get("/api/config").json()["simulation_cur_dt_ts"] >= before
        assert client.get("/api/history/AAPL").json()[-1]["ts"] == updated["reference_ts"]
