# Pricing Engine and Live Order Book

FastAPI backend and Angular frontend for simulated prices and shared live market depth. Search a ticker to load its price history and ten bid/ask levels. Prices advance once per minute; book quantities update once per second. All clients see the same backend-owned liquidity.

## Run backend (uv)

```bash
uv sync --frozen
uv run uvicorn app.main:app --reload
```

Optional simulation datetime (ISO-8601):

```bash
SIMULATION_DT=2024-01-02T11:30:00 uv run uvicorn app.main:app --reload
```

## Run frontend (Angular)

```bash
cd frontend
npm ci
npm start
```

Open `http://localhost:4200`.

The backend API documentation is at `http://127.0.0.1:8000/docs`.

## Notes

- Available tickers: `AAPL`, `MSFT`, `GOOG`, `TSLA`.
- History is capped at 390 points (one trading day of 1-minute bars).
- The default simulation starts January 2, 2024, at 11:30 a.m. New York time. Set `SIMULATION_DT` to change it; naive timestamps use New York time and aware timestamps are converted to it.
- The session is 9:30 a.m. inclusive to 4:00 p.m. exclusive, New York time. Depth freezes outside the session. This is a single-session demo without an exchange holiday calendar.
- Prices have a minimum of $0.11 so ten positive one-cent bid levels remain available.
- Run one backend worker: state is in memory, shared across connections within that process, and resets on restart.
- Trading, matching, balances, and execution-driven prices are reserved for the next milestone. The current book is simulated aggregated liquidity.

## Order book API

- `GET /api/orderbook/{ticker}` initializes and returns the current full snapshot. Tickers are case-insensitive; unsupported tickers return 404.
- `GET /api/orderbook/{ticker}/stream` sends full snapshots as default SSE `message` events. Every connection starts with the current snapshot, including reconnects; missed events are not replayed. Event IDs are per-ticker sequences and reset on server restart. Slow clients skip intermediate snapshots rather than accumulating a queue. SSE comment heartbeats keep closed-market connections alive.
- Snapshot fields: `ticker`, `sequence`, `ts` (simulation epoch seconds), `reference_price`, `reference_ts` (price epoch seconds), `session_status` (`open` or `closed`), `bids`, and `asks`.
- Each level has `price`, integer `quantity`, and `cumulative_quantity`. API bids are sorted highest first; asks lowest first. The UI reverses asks so the best ask sits beside the spread.
- Existing history, latest-price, parameter, and configuration endpoints retain their response formats. The UI uses snapshot reference prices to keep the chart and book aligned without duplicating minute points.

## Verification

```bash
uv run python -m pytest -q
cd frontend
npm run build
```

The API acceptance suite launches real backend processes on temporary local ports. It covers shared state, streaming and reconnects, initialization, session transitions, minute-price alignment, and unsupported symbols.

With both development servers running, use `npm run test:browser` from `frontend/` for browser acceptance checks. See [browser test setup](frontend/tests/README.md) for Playwright/Chrome requirements and environment options.
