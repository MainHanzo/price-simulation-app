# Price Generator · Market Lab

An anonymous synthetic market simulator with its original Market Lab interface:
asset class, simulation model, bar interval, Start/Stop, and a candlestick/volume
chart with zoom and pan. It generates a random price path rather than looking up
named instruments. Time is elapsed simulated time, with no trading-day clock.

The order book belongs to that same anonymous run. Its reference price is the
forming candle’s close, quantities change once per second while running, and
Stop freezes both the chart and depth. Start creates a fresh stochastic run.
The original regime switching, mean reversion, and jump diffusion models are
unchanged. Trading and order matching remain a future milestone.

## Run locally

```sh
uv sync --frozen
HOST=127.0.0.1 PORT=4200 uv run python server.py
```

Open `http://localhost:4200`. The active frontend is `web/`; no Angular build is
needed. The earlier Angular/FastAPI prototype in `frontend/` and `app/` is not
the current application or deployment entrypoint.

## API

- `POST /api/start` takes `asset_class` (`stocks` or `spot_crypto`),
  `simulation_model` (`regime_switching`, `mean_reverting`, or `jump_diffusion`),
  and `bar_interval` (`1m`, `2m`, `5m`, `15m`, `1h`, `2h`, `3h`, or `4h`).
- `GET /api/state?history=1` returns the original simulation/candle payload,
  plus `order_book`. Chart and depth therefore use one consistent snapshot.
- `GET /api/orderbook` returns the active anonymous book, or null before Start.
  Reading depth does not consume pending closed candles.
- `POST /api/stop` freezes the current simulation and book.
- A book contains `run_id`, `sequence`, `ts`, `reference_price`,
  `reference_simulated_seconds`, `status`, `tick_size`, `bids`, and `asks`.
  Each side has ten levels with `price`, positive integer `quantity`, and
  `cumulative_quantity`. Prices use one-cent ticks for normal profile prices;
  very small synthetic prices use a smaller grid to keep all bids positive.

## Verify

```sh
uv run python -m pytest -q
node --test tests/browser/marketlab.test.mjs
```

Browser tests require Playwright and Chrome (or the bundled Codex runtime).
They verify the original controls/style, random simulation, chart/depth
alignment, Stop/restart, responsiveness, and service-error recovery.

## Hosted version

[Price Generator](https://d1duii6i44ll6h.cloudfront.net/price-generator/) uses the
existing ticker-info sign-in. `BASE_PATH=/price-generator` preserves its route.
The production container requires `AUTH_SESSION_URL`; local development can run
without it. See [deployment and rollback](deploy/README.md).
