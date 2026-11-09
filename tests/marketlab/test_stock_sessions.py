"""US stock sessions exercised only through the running HTTP service."""

import time
from typing import Any

import httpx
import pytest


def start(client: httpx.Client, prefix: str, **options: Any) -> dict[str, Any]:
    response = client.post(prefix + "/api/start", json={
        "asset_class": "stocks", "simulation_model": "regime_switching",
        "bar_interval": "1m", "seed": 71, **options,
    })
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("preset,clock,phase", [
    ("pre_open", "09:25:00", "pre_open"), ("opening", "09:30:00", "opening"),
    ("midday", "12:00:00", "midday"), ("closing", "15:30:00", "closing"),
    ("final_minute", "15:59:00", "closing"),
])
def test_presets_and_shared_state(marketlab_server: tuple[httpx.Client, str], preset: str, clock: str, phase: str) -> None:
    client, prefix = marketlab_server
    state = start(client, prefix, session_preset=preset, playback_speed=20)
    assert state["session"]["clock"] == clock
    assert state["session"]["phase"] == phase
    assert state["session"]["timezone"] == "America/New_York"
    assert state["session"]["preset"] == preset
    assert state["session"]["playback_speed"] == 20
    assert state["session"]["simulated_seconds"] == state["order_book"]["reference_simulated_seconds"]
    assert state["session"]["phase"] == state["order_book"]["session_phase"]


def test_preopen_crosses_opening_once_and_stop_freezes_everything(marketlab_server: tuple[httpx.Client, str]) -> None:
    client, prefix = marketlab_server
    initial = start(client, prefix, session_preset="pre_open", playback_speed=600)
    assert initial["current_bar"]["volume"] == 0
    assert initial["session"]["auctions"] == []
    time.sleep(.6)
    state = client.post(prefix + "/api/stop", json={}).json()
    assert state["session"]["phase"] == "opening"
    assert [event["kind"] for event in state["session"]["auctions"]] == ["opening"]
    assert state["session"]["auctions"][0]["volume"] > 0
    time.sleep(.05)
    frozen = client.get(prefix + "/api/state?history=1").json()
    assert frozen["session"] == state["session"]
    assert frozen["order_book"] == state["order_book"]
    assert frozen["current_bar"] == state["current_bar"]


@pytest.mark.parametrize("model", ["regime_switching", "mean_reverting", "jump_diffusion"])
def test_closing_finalizes_once_even_with_long_candles(marketlab_server: tuple[httpx.Client, str], model: str) -> None:
    client, prefix = marketlab_server
    start(client, prefix, session_preset="final_minute", playback_speed=600, bar_interval="4h", simulation_model=model)
    time.sleep(.15)
    state = client.get(prefix + "/api/state?history=1").json()
    assert state["running"] is False
    assert state["session"]["clock"] == "16:00:00"
    assert state["session"]["phase"] == "closed"
    assert state["session"]["seconds_to_close"] == 0
    assert state["current_bar"]["is_closed"] is True
    assert len(state["history"]) == 1
    assert state["history"][-1] == state["current_bar"]
    assert state["current_bar"]["elapsed_simulated_seconds"] == 60
    assert [event["kind"] for event in state["session"]["auctions"]] == ["closing"]
    assert state["session"]["official_close"] == state["current_bar"]["close"]
    assert state["current_bar"]["volume"] >= state["session"]["auctions"][0]["volume"]
    time.sleep(.05)
    again = client.get(prefix + "/api/state?history=1").json()
    assert again["session"] == state["session"]
    assert again["history"] == state["history"]
    assert again["order_book"] == state["order_book"]


def test_speed_is_independent_of_bar_interval(marketlab_server: tuple[httpx.Client, str]) -> None:
    client, prefix = marketlab_server
    elapsed: list[float] = []
    for interval in ("1m", "4h"):
        start(client, prefix, session_preset="midday", playback_speed=120, bar_interval=interval)
        time.sleep(.15)
        state = client.post(prefix + "/api/stop", json={}).json()
        elapsed.append(state["session"]["simulated_seconds"])
    assert all(12 < value < 45 for value in elapsed), elapsed
    assert abs(elapsed[0] - elapsed[1]) < 12


@pytest.mark.parametrize("options", [
    {"session_preset": "unknown"}, {"playback_speed": 0}, {"playback_speed": 601},
    {"playback_speed": True}, {"playback_speed": "NaN"}, {"seed": True},
    {"seed": 1.5}, {"seed": []}, {"session_preset": {}},
    {"playback_speed": 10**400},
])
def test_invalid_settings_preserve_active_run(marketlab_server: tuple[httpx.Client, str], options: dict[str, Any]) -> None:
    client, prefix = marketlab_server
    initial = start(client, prefix)
    response = client.post(prefix + "/api/start", json={
        "asset_class": "stocks", "bar_interval": "1m", **options,
    })
    assert response.status_code == 400
    assert client.get(prefix + "/api/state").json()["run_id"] == initial["run_id"]


def test_restart_resets_session_and_crypto_remains_continuous(marketlab_server: tuple[httpx.Client, str]) -> None:
    client, prefix = marketlab_server
    first = start(client, prefix, session_preset="final_minute", playback_speed=600)
    time.sleep(.15)
    client.get(prefix + "/api/state")
    restarted = start(client, prefix, session_preset="midday")
    assert restarted["run_id"] == first["run_id"] + 1
    assert restarted["session"]["auctions"] == []
    assert restarted["session"]["official_close"] is None
    crypto = start(client, prefix, asset_class="spot_crypto")
    assert crypto["session"] is None
    assert crypto["running"] is True


def test_session_controls_are_served(marketlab_server: tuple[httpx.Client, str]) -> None:
    client, prefix = marketlab_server
    page = client.get(prefix + "/").text
    for identifier in ("sessionPreset", "playbackSpeed", "marketClock", "marketPhase", "auctionSummary"):
        assert f'id="{identifier}"' in page


@pytest.mark.parametrize("body", [[], None, "invalid", 5])
def test_nonobject_json_is_rejected(marketlab_server: tuple[httpx.Client, str], body: Any) -> None:
    import json

    client, prefix = marketlab_server
    response = client.post(prefix + "/api/start", content=json.dumps(body), headers={"Content-Type": "application/json"})
    assert response.status_code == 400
