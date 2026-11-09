# US Stock Sessions Implementation Plan

**Goal:** Model a typical US equity session with coordinated price, volume and book dynamics.
**Architecture:** A pure session schedule supplies shared conditions to the engine and book; the server exposes one consistent snapshot and the existing frontend renders it.
**Tech stack:** Python 3.11, standard HTTP server, vanilla JavaScript/canvas, pytest, Playwright.

## Task 1 — Independent acceptance tests (red)
- [x] Create tests/marketlab/test_stock_sessions.py using the public HTTP routes and existing executable-server fixture.
- [x] Cover presets, validation, interval-independent playback, pre-open/open and final-minute/close transitions, exactly-once auctions, Stop/restart, stock-only behavior, and shared timestamps.
- [x] Run `uv run python -m pytest tests/marketlab/test_stock_sessions.py -q`; confirm missing session fields fail.

## Task 2 — Schedule and engine (unit tests + implementation)
- [x] Create price_generator/market_session.py with presets, bounded speed/seed validation and pure session conditions; test exact boundaries and opening/closing coefficient shapes in tests/test_stock_session_engine.py.
- [x] Extend price_generator/model.py with optional stock session configuration, shared state, explicit playback speed, auction events and closing truncation. Preserve continuous crypto behavior and legacy direct-engine defaults unless session configuration is supplied.
- [x] Unit-test all three models, one-shot vs chunked boundary processing, partial bars, zero-time reads, seeded reproducibility, auction-volume accounting and ensemble opening/midday/closing distributions.

## Task 3 — API and order book (unit tests + implementation)
- [x] Extend price_generator/order_book.py to consume conditions and seed, with simulated refresh time, variable spread/depth, positive grid-aligned prices and persistent imbalance.
- [x] Wire stock defaults/preset/speed/seed through server.py and expose session metadata. Validate before replacing active state; stop at the closing bell.
- [x] Keep shared reference time/price and stopped snapshots stable. Re-run precision tests.

## Task 4 — UI and documentation
- [x] Add session strip and styles in web/session.css, controls in web/index.html, and rendering in web/app.js. Disable stock controls for crypto, restore on reload, show phase/countdown and auction summary, use ET stock labels.
- [x] Retain web/styles.css unchanged; update cache versions for modified assets.
- [x] Add real-browser tests for stock settings, closing, reload and mobile overflow. Update README.md API fields, scope and launch instructions.

## Task 5 — Independent acceptance verification and review
- [x] Run acceptance tests after implementation, diagnose unexpected failures, and fix with regressions.
- [x] Run complete pytest suite and `node --test tests/browser/marketlab.test.mjs`.
- [x] Inspect desktop/mobile screenshots and request independent code review; fix material findings and rerun affected checks.
- [x] Leave verified changes on codex/us-stock-sessions with clear local preview instructions; do not deploy.

## Verification and review
- Baseline: 48 Python tests passed before feature changes.
- Final Python suite: 116 passed.
- Browser suite includes stock session controls, exact close, reload, mobile overflow, existing crypto behavior, service recovery, precision, and both delayed-poll orderings.
- Statistical engine checks cover all three stochastic models over 30 fixed seeds for each of opening, midday and closing.
- Independent review fixes: huge integer validation, stable quote refresh cadence, epsilon-close metadata, and recovery of candles consumed by superseded polls. Reviewer reported no remaining material findings and independently passed both network-race browser regressions.
- Desktop/mobile screenshots inspected. Preview is served from this worktree at http://127.0.0.1:4281. No deployment or remote push.
