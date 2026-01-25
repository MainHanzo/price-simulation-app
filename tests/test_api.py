from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from zoneinfo import ZoneInfo

from app.api import router
from app.engine import PriceEngine


def build_app() -> FastAPI:
    sim_dt = datetime(2024, 1, 2, 11, 30, tzinfo=ZoneInfo("America/New_York"))
    engine = PriceEngine(tickers=["AAPL"], simulation_dt=sim_dt)
    engine._generate_history_for_ticker("AAPL", sim_dt)
    app = FastAPI()
    app.state.engine = engine
    app.state.simulation_cur_dt = sim_dt
    app.state.simulation_dt = sim_dt
    app.include_router(router)
    return app


def test_api_history_latest_params_config():
    app = build_app()
    client = TestClient(app)

    res = client.get("/api/history/AAPL")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    res = client.get("/api/latest/AAPL")
    assert res.status_code == 200
    data = res.json()
    assert "ts" in data and "price" in data

    res = client.get("/api/params/AAPL")
    assert res.status_code == 200
    params = res.json()
    assert "volatility" in params and "drift" in params

    res = client.post("/api/params/AAPL", json={"volatility": 0.33, "drift": 0.12})
    assert res.status_code == 200
    updated = res.json()
    assert updated["volatility"] == 0.33
    assert updated["drift"] == 0.12

    res = client.get("/api/config")
    assert res.status_code == 200
    assert "simulation_cur_dt_ts" in res.text and "simulation_cur_dt_iso" in res.text
