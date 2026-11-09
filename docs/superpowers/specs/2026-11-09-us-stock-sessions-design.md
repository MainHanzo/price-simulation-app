# US stock session simulation

Approved direction: session-aware synthetic US stock behavior; crypto remains continuous.

One simulated Eastern Time session runs from a selectable pre-open (09:25), opening bell (09:30), midday (12:00), closing run-up (15:30), or final minute (15:59) to 16:00. This is an illustrative typical day, without dated holiday or early-close calendars. Stop freezes the run; Start creates a fresh day. Stock playback defaults to 20 simulated seconds per real second, independent of bar interval; supported speeds span 1–600. The stock engine clips advances at phase, auction, candle, and closing boundaries.

A focused session module supplies volatility, volume, spread, depth, quote refresh, and signed imbalance conditions. Opening uncertainty decays smoothly; closing urgency ramps up with more volume and depth and generally tighter spreads. Existing three stochastic models retain their identities. Directional imbalance is seeded per day and persists; its strength follows session conditions. Volume is independent of displayed resting depth.

Pre-open has queued synthetic depth and no continuous trades. Simplified opening and closing auctions generate exactly one event each when crossed: clearing price, paired volume, and imbalance. Opening permits a bounded price gap from the reference previous close; closing records an official closing price and adds auction volume once to the final candle. These are synthetic events, not an executable matching engine. Intraday presets do not invent missed opening volume. At close the partial final candle is finalized and the run stops; no extra empty candle is displayed.

Price, book, and session metadata share elapsed simulated time. Book refreshes follow simulated time rather than wall time. API state includes session phase, clock, countdown, conditions, auctions, preset, and playback speed. Optional seed permits repeatable debugging. Invalid input returns 400 without replacing a running session. Existing fields/routes and small-price precision remain compatible.

UI adds a dedicated session strip with preset, speed, phase, clock/countdown, and auction summary, keeping the existing chart style and controls. Stocks use ET chart labels; crypto keeps elapsed labels. Controls freeze while running; reload restores settings.

Validation includes independent HTTP acceptance tests before implementation, deterministic engine tests for all models and boundaries, statistical comparisons over fixed seed ensembles, and desktop/mobile browser flows. No deployment is included.
