# Price Generator · Market Lab

An anonymous synthetic market simulator with its original Market Lab interface:
asset class, simulation model, bar interval, Start/Stop, and a candlestick/volume
chart with zoom and pan. It generates a random price path rather than looking up
named instruments. Stocks follow a simulated US equity session in Eastern Time;
spot crypto remains a continuous stream with elapsed-time labels.

The order book belongs to that same anonymous run. Its reference price is the
forming candle’s close. Stock depth follows simulated time and session conditions;
crypto quantities change once per real second while running.
Stop freezes both the chart and depth. Start creates a fresh stochastic run.
Regime switching, mean reversion, and jump diffusion all support stock session
conditions. Trading and order matching remain a future milestone.

## US stock sessions

Choose **Pre-open (09:25)**, **Opening bell (09:30)**, **Midday (12:00)**,
**Closing run-up (15:30)**, or **Final minute (15:59)**. Playback speed is
independent of candle interval: the default 20× advances 20 simulated seconds
per real second. Changing the interval changes candle aggregation; changing
speed changes how fast the stock session runs. Crypto retains the original
three-real-seconds-per-candle playback.

Opening uncertainty raises volatility and volume, widens spreads and reduces
displayed depth; it fades over the first 30 minutes. Midday is quieter. Volume,
depth and urgency rise toward the close, while quoted spreads generally tighten.
Seeded buy/sell pressure affects both price drift and book quantities.

Before 09:30, depth represents queued synthetic interest and candle volume is
zero. A simplified opening auction introduces a bounded gap from the previous
close reference. Opening and closing auctions each generate one volume print,
included once in their respective candles. Starting intraday does not invent
an earlier opening print. At 16:00 the closing auction sets the official close,
the final candle (including a partial long candle) is finalized, and the run
stops automatically. Stop freezes everything; Start creates a new run.

This is one **typical synthetic day**, with illustrative coefficients. It has
no date-specific holiday/early-close calendar, after-hours trading, executable
orders, or full auction matching. The auction indications are synthetic previews.

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
- Stock options: `session_preset` (`pre_open`, `opening` [default], `midday`,
  `closing`, `final_minute`) and numeric `playback_speed` (1–600, default 20).
  These options do not affect crypto. Optional integer `seed` (0–4294967295)
  makes engine runs repeatable for the same sequence of time advances.
- Invalid settings return 400 without replacing the active run.
- `GET /api/state?history=1` returns the original simulation/candle payload,
  plus `order_book` and `session`. Chart and depth therefore use one consistent
  snapshot. `session` is null before Start and for crypto; stock sessions contain
  `clock`, `timezone`, `start_seconds`, `simulated_seconds`, `phase`, `phase_label`,
  `seconds_to_close`, `preset`, `playback_speed`, `conditions`, `auctions`,
  `next_auction`, and `official_close` (null until the close).
- `GET /api/orderbook` returns the active anonymous book, or null before Start.
  Reading depth does not consume pending closed candles.
- `POST /api/stop` freezes the current simulation and book.
- A book contains `run_id`, `sequence`, `ts`, `reference_price`,
  `reference_simulated_seconds`, `status`, `tick_size`, `bids`, and `asks`.
  Each side has ten levels with `price`, positive integer `quantity`, and
  `cumulative_quantity`. Prices use one-cent ticks for normal profile prices;
  very small synthetic prices use a smaller grid to keep all bids positive.
  Stock books also contain `session_phase` and signed `imbalance`. Auction events
  contain `kind`, `price`, `volume`, `simulated_seconds`, `imbalance_side`, and
  `imbalance_quantity`. The next-auction indication contains an indicative price,
  countdown, and synthetic imbalance quantity/side.

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
