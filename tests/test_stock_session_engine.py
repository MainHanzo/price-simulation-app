"""Deterministic behavior of the public simulation engine and stock schedule."""

import math
from dataclasses import asdict

import pytest

from price_generator import create_simulator
from price_generator.market_session import USStockSession


def test_schedule_boundaries_and_distinct_open_close_profiles() -> None:
    session = USStockSession("pre_open", 20)
    assert session.conditions(0, .6).phase == "pre_open"
    opening = session.conditions(300, .6)
    assert opening.phase == "opening"
    assert session.conditions(2100, .6).phase == "regular"
    midday = session.conditions(9300, .6)
    closing = session.conditions(23700 - 60, .6)
    assert midday.phase == "midday"
    assert closing.phase == "closing"
    assert session.conditions(23700, .6).phase == "closed"
    assert opening.volatility > closing.volatility > midday.volatility
    assert opening.volume > midday.volume and closing.volume > midday.volume
    assert opening.spread > midday.spread > closing.spread
    assert opening.depth < midday.depth < closing.depth
    assert opening.imbalance > 0 and closing.imbalance > 0


@pytest.mark.parametrize("model", ["regime_switching", "mean_reverting", "jump_diffusion"])
def test_engine_closes_partial_bar_and_counts_auction_once(model: str) -> None:
    engine = create_simulator("stocks", "4h", seed=7, simulation_model=model,
                              stock_session=USStockSession("final_minute", 120))
    result = engine.advance_wall_time(5)
    assert result.simulated_seconds == 60
    assert len(result.completed_bars) == 1
    assert result.forming_bar == result.completed_bars[0]
    assert result.forming_bar.is_closed
    assert engine.session_state["official_close"] == result.forming_bar.close
    assert engine.session_state["auctions"][0]["volume"] <= result.forming_bar.volume
    before = asdict(result.forming_bar)
    assert asdict(engine.advance_wall_time(10).forming_bar) == before
    assert len(engine.session_state["auctions"]) == 1


def test_auction_survives_coincident_bar_boundary_and_chunked_advances() -> None:
    def run(parts: list[float]) -> tuple[list[dict], dict]:
        engine = create_simulator("stocks", "1m", seed=9, stock_session=USStockSession("pre_open", 20))
        bars = []
        for part in parts:
            bars.extend(asdict(bar) for bar in engine.advance_wall_time(part).completed_bars)
        return bars, engine.session_state

    whole, state = run([1185])
    chunked, other = run([15] * 79)
    assert whole == chunked
    assert state == other
    assert [event["kind"] for event in state["auctions"]] == ["opening", "closing"]
    assert sum(bar["volume"] for bar in whole) >= sum(event["volume"] for event in state["auctions"])
    assert whole[-1]["close"] == state["official_close"]


def test_starting_at_open_applies_bounded_gap_and_seed_repeats() -> None:
    first = create_simulator("stocks", "1m", seed=19, stock_session=USStockSession())
    second = create_simulator("stocks", "1m", seed=19, stock_session=USStockSession())
    assert first.current_bar == second.current_bar
    assert first.session_state == second.session_state
    event = first.session_state["auctions"][0]
    assert event["kind"] == "opening" and event["volume"] > 0
    assert abs(math.log(first.current_bar.close / first.profile.starting_price)) <= .02
    assert first.current_bar.open == first.current_bar.close


@pytest.mark.parametrize("model", ["regime_switching", "mean_reverting", "jump_diffusion"])
def test_opening_and_closing_volume_and_opening_volatility_over_seed_ensemble(model: str) -> None:
    measurements: dict[str, tuple[float, float]] = {}
    for preset in ("opening", "midday", "closing"):
        volumes, squares = [], []
        for seed in range(30):
            engine = create_simulator("stocks", "1m", seed=seed, simulation_model=model,
                                      stock_session=USStockSession(preset, 20))
            result = engine.advance_wall_time(30)
            # Ignore the opening-auction candle when measuring continuous activity.
            bars = result.completed_bars[1:]
            volumes.extend(bar.volume for bar in bars)
            squares.extend(math.log(bar.close / bar.open) ** 2 for bar in bars)
        measurements[preset] = (sum(volumes) / len(volumes), sum(squares) / len(squares))
    assert measurements["opening"][0] > measurements["midday"][0] * 2
    assert measurements["closing"][0] > measurements["midday"][0] * 1.5
    assert measurements["opening"][1] > measurements["midday"][1] * 2


def test_stock_speed_does_not_depend_on_candle_interval_and_crypto_is_unaffected() -> None:
    for interval in ("1m", "4h"):
        engine = create_simulator("stocks", interval, seed=1, stock_session=USStockSession("midday", 120))
        assert engine.advance_wall_time(1).simulated_seconds == 120
    crypto = create_simulator("spot_crypto", "1m", seed=1)
    assert crypto.session_state is None
    assert crypto.advance_wall_time(3).simulated_seconds == 60


def test_sessions_cannot_be_applied_to_crypto() -> None:
    with pytest.raises(ValueError, match="stocks"):
        create_simulator("spot_crypto", "1m", stock_session=USStockSession())


def test_huge_integer_speed_is_a_validation_error() -> None:
    with pytest.raises(ValueError, match="playback_speed"):
        USStockSession("opening", 10**400)


def test_close_with_sub_epsilon_remainder_has_consistent_closed_metadata() -> None:
    engine = create_simulator("stocks", "1m", stock_session=USStockSession("final_minute", 1), seed=7)
    result = engine.advance_wall_time(60 - 5e-10)
    assert result.forming_bar.is_closed
    assert engine.session_state["phase"] == "closed"
    assert engine.session_state["clock"] == "16:00:00"
    assert engine.session_state["simulated_seconds"] == 60
    assert result.forming_bar.elapsed_simulated_seconds == 60
