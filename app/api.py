import time as pytime
from typing import List

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()

@router.get("/api/history/{ticker}")
async def get_history(ticker: str, request: Request) -> List[dict]:
    engine = request.app.state.engine
    t = ticker.upper()
    if t not in engine.ticker_params_map:
        raise HTTPException(status_code=404, detail="Unknown ticker")
    async with engine.lock:
        if t not in engine.ticker_history_map:
            engine._generate_history_for_ticker(t, request.app.state.simulation_cur_dt)
    if t not in engine.ticker_history_map:
        raise HTTPException(status_code=404, detail="Unknown ticker")
    async with engine.lock:
        return [{"ts": p.ts, "price": p.price} for p in engine.ticker_history_map[t] if p is not None]


@router.get("/api/latest/{ticker}")
async def get_latest(ticker: str, request: Request) -> dict:
    engine = request.app.state.engine
    t = ticker.upper()
    if t not in engine.ticker_latest_cache:
        raise HTTPException(status_code=404, detail="Unknown ticker")
    async with engine.lock:
        p = engine.ticker_latest_cache[t]
        return {"ts": p.ts, "price": p.price}


@router.get("/api/params/{ticker}")
async def get_params(ticker: str, request: Request) -> dict:
    engine = request.app.state.engine
    t = ticker.upper()
    if t not in engine.ticker_params_map:
        raise HTTPException(status_code=404, detail="Unknown ticker")
    async with engine.lock:
        return {
            "volatility": engine.ticker_params_map[t]["volatility"],
            "drift": engine.ticker_params_map[t]["drift"],
        }


@router.post("/api/params/{ticker}")
async def update_params(ticker: str, payload: dict, request: Request) -> dict:
    engine = request.app.state.engine
    t = ticker.upper()
    if t not in engine.ticker_params_map:
        raise HTTPException(status_code=404, detail="Unknown ticker")
    if "volatility" not in payload or "drift" not in payload:
        raise HTTPException(status_code=400, detail="Missing volatility or drift")
    vol = float(payload["volatility"])
    drift = float(payload["drift"])
    async with engine.lock:
        engine.ticker_params_map[t]["volatility"] = vol
        engine.ticker_params_map[t]["drift"] = drift
    return {"volatility": vol, "drift": drift}


@router.get("/api/config")
async def get_config(request: Request) -> dict:
    app_state = request.app.state
    return {
        "simulation_start_iso": app_state.simulation_dt.isoformat(),
        "server_now_epoch": pytime.time(),
        "simulation_cur_dt_iso": app_state.simulation_cur_dt.isoformat(),
        "simulation_cur_dt_ts": app_state.simulation_cur_dt.timestamp(),
    }
