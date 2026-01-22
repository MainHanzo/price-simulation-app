from typing import List

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()

@router.get("/api/history/{ticker}")
async def get_history(ticker: str, request: Request) -> List[dict]:
    engine = request.app.state.engine
    t = ticker.upper()
    if t not in engine.history:
        raise HTTPException(status_code=404, detail="Unknown ticker")
    async with engine.lock:
        return [{"ts": p.ts, "price": p.price} for p in engine.history[t] if p is not None]


@router.get("/api/latest/{ticker}")
async def get_latest(ticker: str, request: Request) -> dict:
    engine = request.app.state.engine
    t = ticker.upper()
    if t not in engine.latest:
        raise HTTPException(status_code=404, detail="Unknown ticker")
    async with engine.lock:
        p = engine.latest[t]
        return {"ts": p.ts, "price": p.price}


@router.get("/api/params/{ticker}")
async def get_params(ticker: str, request: Request) -> dict:
    engine = request.app.state.engine
    t = ticker.upper()
    if t not in engine.params:
        raise HTTPException(status_code=404, detail="Unknown ticker")
    async with engine.lock:
        return {"volatility": engine.params[t]["volatility"], "drift": engine.params[t]["drift"]}

