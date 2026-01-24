# Pricing Engine (Step 1)

Minimal FastAPI backend with a static frontend that searches a ticker, loads price history, and polls the latest price every 60 seconds.

## Run backend (uv)

```bash
uv venv --python 3.11.9
uv sync
uv run uvicorn app.main:app --reload
```

Optional simulation datetime (ISO-8601):

```bash
SIMULATION_DT=2024-01-02T11:30:00 uv run uvicorn app.main:app --reload
```

## Run frontend (Angular)

```bash
cd frontend
npm install
npm start
```

Open `http://localhost:4200`.

Open `http://127.0.0.1:8000` in your browser.

## Notes

- Available tickers: `AAPL`, `MSFT`, `GOOG`, `TSLA`.
- History is capped at 390 points (one trading day of 1-minute bars).

## workflow

server receive request from client -> server note timestamp -> server generate history of ticker requested -> server check history completeness -> history returned to client