"""Observable Market Lab flow: no named symbols or trading-day clock."""

import time
from typing import Any

import httpx
import pytest


def assert_depth(state: dict[str, Any]) -> None:
    book = state["order_book"]
    assert book["run_id"] == state["run_id"]
    assert book["reference_price"] == state["current_bar"]["close"]
    assert book["reference_simulated_seconds"] == state["current_bar"]["start_simulated_seconds"] + state["current_bar"]["elapsed_simulated_seconds"]
    assert "ticker" not in state and "ticker" not in book
    assert book["bids"][0]["price"] < book["reference_price"] < book["asks"][0]["price"]
    for side, reverse in (("bids", True), ("asks", False)):
        levels = book[side]
        assert len(levels) == 10
        prices = [level["price"] for level in levels]
        assert prices == sorted(set(prices), reverse=reverse)
        total = 0
        for level in levels:
            assert level["price"] > 0
            assert isinstance(level["quantity"], int) and level["quantity"] > 0
            total += level["quantity"]
            assert level["cumulative_quantity"] == total


def test_original_ui_and_idle_state_have_no_symbol_selection(marketlab_server: tuple[httpx.Client, str]) -> None:
    client, prefix = marketlab_server
    page = client.get(prefix + "/").text
    assert "<title>Price Generator · Market Lab</title>" in page
    assert 'id="assetClass"' in page and 'id="simulationModel"' in page and 'id="barInterval"' in page
    assert 'id="ticker-input"' not in page and "AAPL" not in page and "New York time" not in page
    state = client.get(prefix + "/api/state?history=1").json()
    assert state["running"] is False and state["order_book"] is None
    assert client.get(prefix + "/api/orderbook").json() is None
    assert client.get(prefix + "/api/orderbook/AAPL").status_code == 404


@pytest.mark.parametrize("asset,model", [("stocks", "regime_switching"), ("stocks", "mean_reverting"), ("stocks", "jump_diffusion"), ("spot_crypto", "regime_switching"), ("spot_crypto", "mean_reverting"), ("spot_crypto", "jump_diffusion")])
def test_original_random_models_drive_candles_and_book(marketlab_server: tuple[httpx.Client, str], asset: str, model: str) -> None:
    client, prefix = marketlab_server
    response = client.post(prefix + "/api/start", json={"asset_class": asset, "bar_interval": "1m", "simulation_model": model})
    assert response.status_code == 200
    state = response.json()
    assert state["asset_class"] == asset and state["simulation_model"] == model
    assert state["current_bar"]["is_synthetic"] is True
    assert_depth(state)
    quantities = [level["quantity"] for level in state["order_book"]["bids"]]
    time.sleep(1.1)
    updated = client.get(prefix + "/api/state").json()
    assert_depth(updated)
    assert updated["current_bar"]["elapsed_simulated_seconds"] > 0
    assert updated["order_book"]["sequence"] > state["order_book"]["sequence"]
    assert [level["quantity"] for level in updated["order_book"]["bids"]] != quantities
    stopped = client.post(prefix + "/api/stop", json={})
    assert stopped.status_code == 200
    frozen = stopped.json()
    assert frozen["running"] is False and frozen["order_book"]["status"] == "stopped"
    time.sleep(0.1)
    assert client.get(prefix + "/api/state").json()["order_book"] == frozen["order_book"]


def test_book_reads_preserve_closed_candles_and_restart_resets_run(marketlab_server: tuple[httpx.Client, str]) -> None:
    client, prefix = marketlab_server
    parameters = {"asset_class": "stocks", "bar_interval": "1m", "simulation_model": "regime_switching"}
    first = client.post(prefix + "/api/start", json=parameters).json()
    time.sleep(3.2)
    client.get(prefix + "/api/orderbook")
    client.get(prefix + "/api/orderbook")
    state = client.get(prefix + "/api/state").json()
    assert state["closed_bars"], "Reading depth must not consume the chart's pending candles"
    assert_depth(state)
    restarted = client.post(prefix + "/api/start", json={**parameters, "asset_class": "spot_crypto", "bar_interval": "5m"}).json()
    assert restarted["run_id"] == first["run_id"] + 1
    assert restarted["order_book"]["sequence"] == 1
    assert restarted["current_bar"]["elapsed_simulated_seconds"] == 0
    assert_depth(restarted)
