import time as pytime
import asyncio
import json
from collections.abc import AsyncIterator
from typing import List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

router = APIRouter()


async def ensure_book(ticker: str, request: Request) -> str:
    engine = request.app.state.engine
    t = ticker.upper()
    if t not in engine.ticker_params_map:
        raise HTTPException(status_code=404, detail="Unknown ticker")
    async with engine.lock:
        engine.ticker_requested.add(t)
        if t not in engine.ticker_latest_cache:
            engine._generate_history_for_ticker(t, request.app.state.simulation_cur_dt)
        if t not in request.app.state.orderbook.snapshots:
            point = engine.ticker_latest_cache[t]
            request.app.state.orderbook.update(t, point.price, point.ts, request.app.state.simulation_cur_dt)
    return t


@router.get("/api/orderbook/{ticker}")
async def get_orderbook(ticker: str, request: Request) -> dict:
    t = await ensure_book(ticker, request)
    return request.app.state.orderbook.snapshots[t].to_dict()


@router.get("/api/orderbook/{ticker}/stream")
async def stream_orderbook(ticker: str, request: Request) -> StreamingResponse:
    t = await ensure_book(ticker, request)

    async def events() -> AsyncIterator[str]:
        last_sequence = None
        last_sent = pytime.monotonic()
        while not await request.is_disconnected():
            snapshot = request.app.state.orderbook.snapshots[t]
            if snapshot.sequence != last_sequence:
                last_sequence = snapshot.sequence
                last_sent = pytime.monotonic()
                yield f"id: {snapshot.sequence}\ndata: {json.dumps(snapshot.to_dict())}\n\n"
            elif pytime.monotonic() - last_sent >= 2:
                last_sent = pytime.monotonic()
                yield ": heartbeat\n\n"
            await asyncio.sleep(0.1)

    return StreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@router.get("/api/history/{ticker}")
async def get_history(ticker: str, request: Request) -> List[dict]:
    engine = request.app.state.engine
    t = ticker.upper()
    if t not in engine.ticker_params_map:
        raise HTTPException(status_code=404, detail="Unknown ticker")
    engine.ticker_requested.add(t)
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
    engine.ticker_requested.add(t)
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
