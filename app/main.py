import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.engine import PriceEngine


app = FastAPI()
engine = PriceEngine(tickers=["AAPL", "MSFT", "GOOG", "TSLA"])
app.state.engine = engine
app.include_router(router)

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.on_event("startup")
async def start_generator() -> None:
    async def loop() -> None:
        while True:
            await engine.step()
            await asyncio.sleep(60)

    asyncio.create_task(loop())


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")
