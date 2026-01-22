# Pricing Engine (Step 1)

Minimal FastAPI backend with a static frontend that searches a ticker, loads price history, and polls the latest price every 60 seconds.

## Run (uv)

```bash
uv venv --python 3.11.9
uv sync
uv run uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000` in your browser.

## Notes

- Available tickers: `AAPL`, `MSFT`, `GOOG`, `TSLA`.
- History is capped at 390 points (one trading day of 1-minute bars).
