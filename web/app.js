const MAX_HISTORY_BARS = 5_000;
const POLL_INTERVAL_MS = 200;
const DEFAULT_BAR_SPACING = 9;
const MIN_BAR_SPACING = 5;
const MAX_BAR_SPACING = 36;
const APP_BASE_PATH = window.location.pathname.startsWith('/price-generator') ? '/price-generator' : '';

const canvas = document.querySelector('#priceChart');
const context = canvas.getContext('2d');
const frame = document.querySelector('#chartFrame');
const tooltip = document.querySelector('#chartTooltip');
const emptyState = document.querySelector('#chartEmpty');
const assetSelect = document.querySelector('#assetClass');
const intervalSelect = document.querySelector('#barInterval');
const simulationModelSelect = document.querySelector('#simulationModel');
const sessionPresetSelect = document.querySelector('#sessionPreset');
const playbackSpeedSelect = document.querySelector('#playbackSpeed');
const modelDescription = document.querySelector('#modelDescription');
const startButton = document.querySelector('#startButton');
const stopButton = document.querySelector('#stopButton');
const zoomInButton = document.querySelector('#zoomIn');
const zoomOutButton = document.querySelector('#zoomOut');
const resetZoomButton = document.querySelector('#resetZoom');
const latestButton = document.querySelector('#latestButton');
const visibleCount = document.querySelector('#visibleCount');
const streamState = document.querySelector('#streamState');
const streamStateText = document.querySelector('#streamStateText');
const errorMessage = document.querySelector('#errorMessage');

let bars = [];
let formingBar = null;
let runId = null;
let latestState = null;
let hoverIndex = -1;
let chartLayout = null;
let pollInFlight = false;
let controlRequestInFlight = false;
let stateGeneration = 0;
let recoverHistoryOnPoll = false;
let barSpacing = DEFAULT_BAR_SPACING;
let rightOffset = 0;
let followLatest = true;
let dragState = null;

const volumeFormat = new Intl.NumberFormat(undefined, { maximumFractionDigits: 4 });

const modelDescriptions = {
  regime_switching: 'A mix of rising, sideways, and falling phases, with noisy volume that responds to price moves.',
  mean_reverting: 'Price wanders around its generated baseline and tends to return toward it.',
  jump_diffusion: 'A noisy price path with occasional sudden jumps and stronger volume around large moves.',
};

function formatPrice(value) {
  if (!Number.isFinite(value)) return '—';
  const digits = value >= 100 ? 2 : value >= 1 ? 3 : 5;
  return new Intl.NumberFormat(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function formatVolume(value) {
  return Number.isFinite(value) ? volumeFormat.format(value) : '—';
}

function formatElapsed(seconds) {
  const totalMinutes = Math.floor(Math.max(0, seconds) / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return `+${String(hours).padStart(3, '0')}h ${String(minutes).padStart(2, '0')}m`;
}

function formatMarketTime(elapsed, withSeconds = false) {
  if (!latestState?.session) return formatElapsed(elapsed);
  const seconds = Math.floor(latestState.session.start_seconds + elapsed);
  const clock = `${String(Math.floor(seconds / 3600)).padStart(2, '0')}:${String(Math.floor(seconds / 60) % 60).padStart(2, '0')}`;
  return withSeconds ? `${clock}:${String(seconds % 60).padStart(2, '0')} ET` : `${clock} ET`;
}

const sessionDescriptions = {
  pre_open: 'Queued liquidity builds before the opening auction; continuous trading has not started.',
  opening: 'Price discovery is fast: elevated volume and volatility, wider spreads, and less stable depth.',
  regular: 'Normal trading conditions, with persistent buy or sell pressure and changing liquidity.',
  midday: 'A quieter stretch: lower volume, calmer price changes, and slower liquidity updates.',
  closing: 'Trading urgency rises: more volume, deeper liquidity, and generally tighter spreads.',
  closed: 'The closing auction has set the official close. Start a new stream to simulate another session.',
};

function renderSession(state) {
  const session = state.session;
  document.querySelector('#stockSession').hidden = assetSelect.value !== 'stocks';
  document.querySelector('#timeAxisNote').textContent = session
    ? 'US stocks use Eastern market time · One typical day, without a holiday calendar.'
    : 'Time axis uses elapsed simulation time, not calendar dates.';
  if (!session) return;
  document.querySelector('#marketClock').textContent = `${session.clock} ET`;
  document.querySelector('#marketPhase').textContent = session.phase_label;
  const remaining = Math.ceil(session.seconds_to_close);
  const countdown = remaining >= 3600
    ? `${Math.floor(remaining / 3600)}h ${Math.floor(remaining / 60) % 60}m`
    : remaining >= 60 ? `${Math.floor(remaining / 60)}m ${remaining % 60}s` : `${remaining}s`;
  document.querySelector('#sessionCountdown').textContent = session.phase === 'closed' ? 'Session complete'
    : `${countdown} to close${state.running ? '' : ' · Stopped'}`;
  document.querySelector('#sessionContext').textContent = sessionDescriptions[session.phase];
  const events = session.auctions.map((auction) => `${auction.kind === 'opening' ? 'Opening' : 'Closing'} auction: ${formatPrice(auction.price)} · ${formatVolume(auction.volume)} shares`);
  const upcoming = session.next_auction;
  if (upcoming && (session.phase === 'pre_open' || session.phase === 'closing')) {
    events.push(`${upcoming.kind === 'opening' ? 'Opening' : 'Closing'} indication: ${formatPrice(upcoming.indicative_price)} · ${formatVolume(upcoming.imbalance_quantity)} shares ${upcoming.imbalance_side} imbalance`);
  }
  document.querySelector('#auctionSummary').textContent = events.join(' / ') || 'Next event: closing auction at 16:00 ET.';
}

function setError(message = '') {
  errorMessage.textContent = message;
  errorMessage.hidden = !message;
}

function renderOrderBook(book, unavailable = false) {
  const status = document.querySelector('#orderBookStatus');
  status.dataset.state = unavailable ? 'unavailable' : book?.status || 'ready';
  status.textContent = unavailable ? 'Unavailable · retrying' : book ? (book.status === 'running' ? 'Running · simulated liquidity' : 'Stopped · last snapshot') : 'Ready to start';
  if (!unavailable && book?.session_phase === 'closed') status.textContent = 'Market closed · last snapshot';
  const levels = document.querySelector('#orderBookLevels');
  const empty = document.querySelector('#orderBookEmpty');
  if (unavailable) {
    if (levels.hidden) empty.textContent = 'Market depth is unavailable. Retrying with the simulation.';
    return;
  }
  levels.hidden = !book;
  empty.hidden = Boolean(book);
  if (!book) {
    empty.textContent = 'Start a simulation to generate market depth.';
    return;
  }
  const digits = Math.max(0, -Math.floor(Math.log10(book.tick_size || .01)));
  const quoteFormat = new Intl.NumberFormat(undefined, digits <= 20
    ? { minimumFractionDigits: digits, maximumFractionDigits: digits }
    : { notation: 'scientific', maximumSignificantDigits: 15 });
  const quote = (value) => quoteFormat.format(value);
  document.querySelector('#orderBookReference').textContent = formatPrice(book.reference_price);
  document.querySelector('#orderBookSpread').textContent = book.asks.length && book.bids.length ? quote(book.asks[0].price - book.bids[0].price) : '—';
  for (const [side, selector] of [['ask', '#orderBookAsks'], ['bid', '#orderBookBids']]) {
    const source = side === 'ask' ? book.asks : book.bids;
    const rows = side === 'ask' ? [...source].reverse() : source;
    const total = Math.max(1, ...source.map((level) => level.cumulative_quantity));
    const fragment = document.createDocumentFragment();
    for (const level of rows) {
      const row = document.createElement('div');
      row.className = 'book-level';
      row.dataset.bookSide = side;
      const depth = document.createElement('span');
      depth.className = 'book-depth';
      depth.style.width = `${Math.max(0, Math.min(100, level.cumulative_quantity / total * 100))}%`;
      row.append(depth);
      for (const [value, className] of [[quote(level.price), 'book-price'], [formatVolume(level.quantity), ''], [formatVolume(level.cumulative_quantity), '']]) {
        const cell = document.createElement('span');
        cell.className = className;
        cell.textContent = value;
        row.append(cell);
      }
      fragment.append(row);
    }
    document.querySelector(selector).replaceChildren(fragment);
  }
}

function setRunState(running) {
  streamState.dataset.state = running ? 'running' : 'stopped';
  streamStateText.textContent = running ? 'STREAMING' : 'READY TO START';
  startButton.hidden = running;
  stopButton.hidden = !running;
  assetSelect.disabled = running;
  intervalSelect.disabled = running;
  simulationModelSelect.disabled = running;
  sessionPresetSelect.disabled = running;
  playbackSpeedSelect.disabled = running;
  if (latestState?.session?.phase === 'closed') streamStateText.textContent = 'SESSION COMPLETE';
}

function updateMetrics(state) {
  const bar = state.current_bar;
  const priceElement = document.querySelector('#lastPrice');
  const moveElement = document.querySelector('#netMove');
  const volumeElement = document.querySelector('#barVolume');
  const elapsedElement = document.querySelector('#elapsedTime');
  const volumeUnitElement = document.querySelector('#volumeUnit');

  if (!bar) {
    priceElement.textContent = '—';
    moveElement.textContent = '—';
    volumeElement.textContent = '—';
    elapsedElement.textContent = '+000h 00m';
    volumeUnitElement.textContent = '';
    return;
  }

  priceElement.textContent = formatPrice(bar.close);
  const baseline = state.start_price || (bars.length ? bars[0].open : bar.open);
  const change = baseline ? ((bar.close / baseline) - 1) * 100 : 0;
  moveElement.textContent = `${change >= 0 ? '+' : ''}${change.toFixed(2)}%`;
  moveElement.className = change > 0.0001 ? 'positive-value' : change < -0.0001 ? 'negative-value' : 'neutral-value';
  volumeElement.textContent = formatVolume(bar.volume);
  volumeUnitElement.textContent = bar.volume_unit;
  elapsedElement.textContent = formatElapsed(bar.start_simulated_seconds + bar.elapsed_simulated_seconds);
}

function applyState(state, { useHistory = false, recoverHistory = false } = {}) {
  if (state.run_id !== runId) {
    runId = state.run_id;
    bars = useHistory ? [...(state.history || [])] : [];
    hoverIndex = -1;
    barSpacing = DEFAULT_BAR_SPACING;
    rightOffset = 0;
    followLatest = true;
    if (state.asset_class) assetSelect.value = state.asset_class;
    if (state.bar_interval) intervalSelect.value = state.bar_interval;
    if (state.simulation_model) simulationModelSelect.value = state.simulation_model;
    if (state.session) {
      sessionPresetSelect.value = state.session.preset;
      // API clients can choose any speed from 1–600; retain it on reload.
      const speed = String(state.session.playback_speed);
      if (![...playbackSpeedSelect.options].some((option) => option.value === speed)) {
        playbackSpeedSelect.add(new Option(`${speed}×`, speed));
      }
      playbackSpeedSelect.value = speed;
    }
  }
  if (useHistory && state.history) bars = [...state.history];
  if (!useHistory) {
    const receivedBars = state.closed_bars || [];
    if (!followLatest) rightOffset += receivedBars.length;
    bars.push(...receivedBars);
  }
  if (recoverHistory && state.history) {
    const before = bars.length;
    bars = [...new Map([...bars, ...state.history].map((bar) => [bar.start_simulated_seconds, bar])).values()]
      .sort((a, b) => a.start_simulated_seconds - b.start_simulated_seconds);
    if (!followLatest) rightOffset += bars.length - before;
  }
  if (bars.length > MAX_HISTORY_BARS) {
    const removed = bars.length - MAX_HISTORY_BARS;
    bars = bars.slice(removed);
    rightOffset = Math.max(0, rightOffset - removed);
  }
  formingBar = state.current_bar;
  latestState = state;

  setRunState(state.running);
  updateMetrics(state);
  renderOrderBook(state.order_book);
  renderSession(state);
  const intervalName = intervalSelect.options[intervalSelect.selectedIndex]?.textContent || 'Elapsed simulated time';
  const modelLabel = state.model_label || simulationModelSelect.options[simulationModelSelect.selectedIndex]?.textContent || 'Simulation';
  document.querySelector('#chartSubtitle').textContent = `${modelLabel} · ${intervalName} bars · ${state.session ? 'US stock session · ET' : 'elapsed simulated time'}`;
  modelDescription.textContent = modelDescriptions[simulationModelSelect.value] || modelDescriptions.regime_switching;
  emptyState.hidden = Boolean(formingBar);
  updateLatestButton();
  drawChart();
}

async function requestJson(path, options = {}) {
  const response = await fetch(`${APP_BASE_PATH}${path}`, {
    cache: 'no-store',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const payload = await response.json();
  if (response.status === 401) {
    window.location.reload();
    throw new Error('Your ticker info session has expired. Sign in to continue.');
  }
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload;
}

async function pollState() {
  if (pollInFlight || controlRequestInFlight) return;
  pollInFlight = true;
  const generation = stateGeneration;
  try {
    const firstRequest = runId === null;
    const recoverHistory = recoverHistoryOnPoll;
    const state = await requestJson(`/api/state${firstRequest || recoverHistory ? '?history=1' : ''}`);
    if (generation !== stateGeneration) {
      recoverHistoryOnPoll = true;
      return;
    }
    applyState(state, { useHistory: firstRequest, recoverHistory });
    recoverHistoryOnPoll = false;
    setError('');
  } catch (error) {
    if (generation !== stateGeneration) {
      recoverHistoryOnPoll = true;
      return;
    }
    setError(`The simulation service is unavailable: ${error.message}`);
    renderOrderBook(null, true);
  } finally {
    pollInFlight = false;
  }
}

document.querySelector('#controls').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (controlRequestInFlight) return;
  controlRequestInFlight = true;
  stateGeneration++;
  startButton.disabled = true;
  setError('');
  try {
    const state = await requestJson('/api/start', {
      method: 'POST',
      body: JSON.stringify({
        asset_class: assetSelect.value,
        bar_interval: intervalSelect.value,
        simulation_model: simulationModelSelect.value,
        session_preset: sessionPresetSelect.value,
        playback_speed: Number(playbackSpeedSelect.value),
      }),
    });
    bars = [];
    hoverIndex = -1;
    applyState(state);
  } catch (error) {
    setError(error.message);
  } finally {
    startButton.disabled = false;
    controlRequestInFlight = false;
  }
});

simulationModelSelect.addEventListener('change', () => {
  modelDescription.textContent = modelDescriptions[simulationModelSelect.value];
  const modelLabel = simulationModelSelect.options[simulationModelSelect.selectedIndex]?.textContent || 'Simulation';
  const intervalName = intervalSelect.options[intervalSelect.selectedIndex]?.textContent || 'Elapsed simulated time';
  document.querySelector('#chartSubtitle').textContent = `${modelLabel} · ${intervalName} bars · elapsed simulated time`;
});

assetSelect.addEventListener('change', () => {
  document.querySelector('#stockSession').hidden = assetSelect.value !== 'stocks';
});

intervalSelect.addEventListener('change', () => {
  const modelLabel = simulationModelSelect.options[simulationModelSelect.selectedIndex]?.textContent || 'Simulation';
  const intervalName = intervalSelect.options[intervalSelect.selectedIndex]?.textContent || 'Elapsed simulated time';
  document.querySelector('#chartSubtitle').textContent = `${modelLabel} · ${intervalName} bars · elapsed simulated time`;
});

stopButton.addEventListener('click', async () => {
  if (controlRequestInFlight) return;
  controlRequestInFlight = true;
  stateGeneration++;
  stopButton.disabled = true;
  try {
    const state = await requestJson('/api/stop', { method: 'POST', body: '{}' });
    // A superseded poll may have consumed closed candles. Recover them without
    // discarding older chart history already loaded in this browser.
    applyState(state, { recoverHistory: true });
  } catch (error) {
    setError(error.message);
  } finally {
    stopButton.disabled = false;
    controlRequestInFlight = false;
  }
});

function visibleBars() {
  const result = [...bars];
  if (formingBar && (!formingBar.is_closed || result.at(-1)?.start_simulated_seconds !== formingBar.start_simulated_seconds)) result.push(formingBar);
  return result;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function updateLatestButton() {
  const isLatest = followLatest || rightOffset < 0.25;
  latestButton.classList.toggle('latest-active', isLatest);
  latestButton.setAttribute('aria-pressed', String(isLatest));
}

function zoomAt(nextSpacing, anchorX = null) {
  const next = clamp(nextSpacing, MIN_BAR_SPACING, MAX_BAR_SPACING);
  if (chartLayout?.data.length && next !== barSpacing) {
    const { data, endIndex, plotRight, left, plotWidth } = chartLayout;
    const x = clamp(anchorX ?? (left + plotWidth / 2), left, plotRight);
    const anchorIndex = clamp(
      endIndex - ((plotRight - x) / barSpacing - 0.5),
      0,
      data.length - 1,
    );
    const nextEndIndex = anchorIndex + ((plotRight - x) / next - 0.5);
    rightOffset = clamp(data.length - 1 - nextEndIndex, 0, data.length - 1);
    followLatest = rightOffset < 0.25;
    hoverIndex = -1;
    tooltip.classList.remove('visible');
    tooltip.setAttribute('aria-hidden', 'true');
  }
  barSpacing = next;
  drawChart();
}

zoomInButton.addEventListener('click', () => zoomAt(barSpacing * 1.25));
zoomOutButton.addEventListener('click', () => zoomAt(barSpacing / 1.25));
resetZoomButton.addEventListener('click', () => {
  barSpacing = DEFAULT_BAR_SPACING;
  rightOffset = 0;
  followLatest = true;
  drawChart();
});
latestButton.addEventListener('click', () => {
  rightOffset = 0;
  followLatest = true;
  updateLatestButton();
  drawChart();
});

canvas.addEventListener('wheel', (event) => {
  if (!chartLayout?.data.length) return;
  event.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const x = event.clientX - rect.left;
  zoomAt(barSpacing * Math.exp(-event.deltaY * 0.001), x);
}, { passive: false });

function beginChartDrag(event) {
  if (event.button !== 0 || !chartLayout?.data.length) return;
  if (dragState) return;
  dragState = {
    pointerId: event.pointerId ?? null,
    startX: event.clientX,
    startOffset: rightOffset,
    moved: false,
  };
  canvas.classList.add('is-panning');
  if (event.pointerId !== undefined) {
    try { canvas.setPointerCapture(event.pointerId); } catch { /* Keep drag available without pointer capture. */ }
  }
}

canvas.addEventListener('pointerdown', beginChartDrag);
canvas.addEventListener('mousedown', beginChartDrag);

function drawChart() {
  const bounds = frame.getBoundingClientRect();
  if (!bounds.width || !bounds.height) return;
  const pixelRatio = window.devicePixelRatio || 1;
  canvas.width = Math.round(bounds.width * pixelRatio);
  canvas.height = Math.round(bounds.height * pixelRatio);
  context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  context.clearRect(0, 0, bounds.width, bounds.height);

  const width = bounds.width;
  const height = bounds.height;
  const data = visibleBars();
  const left = width < 600 ? 15 : 25;
  const right = width < 600 ? 62 : 82;
  const top = 25;
  const bottom = width < 600 ? 32 : 37;
  const volumeHeight = Math.max(74, Math.min(112, height * 0.2));
  const dividerGap = 20;
  const priceBottom = height - bottom - volumeHeight - dividerGap;
  const plotRight = width - right;
  const plotWidth = plotRight - left;
  const priceTop = top;
  const priceHeight = Math.max(100, priceBottom - priceTop);

  const maxOffset = Math.max(0, data.length - 1);
  rightOffset = clamp(rightOffset, 0, maxOffset);
  const endIndex = Math.max(0, data.length - 1 - rightOffset);
  const firstVisibleIndex = Math.max(0, Math.ceil(endIndex - plotWidth / barSpacing + 0.5));
  const lastVisibleIndex = Math.min(data.length - 1, Math.floor(endIndex));
  const countInView = Math.max(0, lastVisibleIndex - firstVisibleIndex + 1);
  const firstDrawIndex = Math.max(0, Math.floor(endIndex - plotWidth / barSpacing) - 1);
  const lastDrawIndex = lastVisibleIndex;
  chartLayout = {
    left, right, top, bottom, volumeHeight, priceBottom, plotWidth, plotRight,
    priceHeight, data, width, height, endIndex, firstVisibleIndex,
    lastVisibleIndex, firstDrawIndex, lastDrawIndex, barSpacing,
  };
  visibleCount.textContent = `${countInView} candles`;
  updateLatestButton();
  drawChartBackground(width, height, left, right, priceTop, priceBottom, volumeHeight, bottom);

  if (!data.length) {
    drawEmptyGridLabels(width, height, left, right, priceTop, priceBottom);
    return;
  }

  const visibleData = data.slice(firstDrawIndex, lastDrawIndex + 1);
  const minPrice = Math.min(...visibleData.map((bar) => bar.low));
  const maxPrice = Math.max(...visibleData.map((bar) => bar.high));
  const spread = Math.max(maxPrice - minPrice, Math.abs(maxPrice) * 0.001, 0.00001);
  const lower = minPrice - spread * 0.12;
  const upper = maxPrice + spread * 0.12;
  const mapPrice = (price) => priceTop + ((upper - price) / (upper - lower)) * priceHeight;
  const candleWidth = Math.max(2, barSpacing * 0.68);

  drawPriceGrid(width, left, right, priceTop, priceBottom, lower, upper, mapPrice);
  drawVolumeGrid(width, left, right, priceBottom, volumeHeight, bottom);
  drawTimeLabels(data, width, left, plotRight, plotWidth, height - bottom + 9, barSpacing, endIndex, firstVisibleIndex, lastVisibleIndex);

  const maxVolume = Math.max(...visibleData.map((bar) => bar.volume), 1);
  visibleData.forEach((bar, localIndex) => {
    const index = firstDrawIndex + localIndex;
    const centerX = plotRight - (endIndex - index + 0.5) * barSpacing;
    if (centerX + candleWidth / 2 < left || centerX - candleWidth / 2 > plotRight) return;
    const isForming = index === data.length - 1 && !bar.is_closed;
    const rising = bar.close >= bar.open;
    const color = rising ? '#79d394' : '#f07b6e';
    const highY = mapPrice(bar.high);
    const lowY = mapPrice(bar.low);
    const openY = mapPrice(bar.open);
    const closeY = mapPrice(bar.close);
    context.strokeStyle = color;
    context.lineWidth = isForming ? 1.25 : 1;
    context.globalAlpha = isForming ? 0.95 : 0.82;
    context.beginPath();
    context.moveTo(centerX, highY);
    context.lineTo(centerX, lowY);
    context.stroke();
    const bodyTop = Math.min(openY, closeY);
    const bodyHeight = Math.max(1.5, Math.abs(openY - closeY));
    if (isForming) {
      context.setLineDash([3, 2]);
      context.lineWidth = 1.3;
      context.strokeRect(centerX - candleWidth / 2, bodyTop, candleWidth, bodyHeight);
      context.setLineDash([]);
    } else {
      context.fillStyle = color;
      context.fillRect(centerX - candleWidth / 2, bodyTop, candleWidth, bodyHeight);
    }
    context.globalAlpha = 1;

    const volumeTop = priceBottom + 20 + volumeHeight * (1 - (bar.volume / maxVolume));
    const volumeBarHeight = Math.max(1, height - bottom - volumeTop);
    context.globalAlpha = isForming ? 0.88 : 0.47;
    context.fillStyle = color;
    context.fillRect(centerX - candleWidth / 2, volumeTop, candleWidth, volumeBarHeight);
    context.globalAlpha = 1;
  });

  const latestIndex = data.length - 1;
  if (latestIndex >= firstVisibleIndex && latestIndex <= lastVisibleIndex) {
    const last = data[latestIndex];
    const lastY = mapPrice(last.close);
    context.save();
    context.setLineDash([4, 4]);
    context.strokeStyle = last.close >= last.open ? 'rgba(132, 221, 158, .65)' : 'rgba(240, 123, 110, .65)';
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(left, lastY);
    context.lineTo(plotRight + 1, lastY);
    context.stroke();
    context.restore();
    drawPriceTag(plotRight + 7, lastY, formatPrice(last.close), last.close >= last.open);
  }
  if (hoverIndex >= firstDrawIndex && hoverIndex <= lastDrawIndex) drawCrosshair(hoverIndex, mapPrice);
}

function drawChartBackground(width, height, left, right, priceTop, priceBottom, volumeHeight, bottom) {
  context.fillStyle = '#12241f';
  context.fillRect(0, 0, width, height);
  context.fillStyle = 'rgba(6, 17, 13, .20)';
  context.fillRect(0, priceBottom + 18, width, height - priceBottom - 18);
  context.fillStyle = '#a5b2a8';
  context.font = '9px "DM Mono", monospace';
  context.textBaseline = 'middle';
  context.fillText('PRICE  /  SYNTHETIC', left, 12);
  const unit = latestState?.current_bar?.volume_unit || 'quantity';
  context.textAlign = 'left';
  context.fillText(`VOLUME  /  ${unit.toUpperCase()}`, left, priceBottom + 9);
  context.textAlign = 'left';
  context.strokeStyle = 'rgba(223, 232, 218, .12)';
  context.beginPath();
  context.moveTo(left, priceBottom + 18);
  context.lineTo(width - right, priceBottom + 18);
  context.stroke();
  context.textBaseline = 'alphabetic';
}

function drawEmptyGridLabels(width, height, left, right, priceTop, priceBottom) {
  context.save();
  context.strokeStyle = 'rgba(223,232,218,.055)';
  context.setLineDash([2, 6]);
  for (let i = 1; i <= 4; i += 1) {
    const y = priceTop + ((priceBottom - priceTop) * i) / 5;
    context.beginPath();
    context.moveTo(left, y);
    context.lineTo(width - right, y);
    context.stroke();
  }
  context.restore();
}

function drawPriceGrid(width, left, right, priceTop, priceBottom, lower, upper, mapPrice) {
  const lines = 4;
  context.save();
  context.font = '10px "DM Mono", monospace';
  context.textBaseline = 'middle';
  for (let index = 0; index <= lines; index += 1) {
    const value = upper - ((upper - lower) * index) / lines;
    const y = mapPrice(value);
    context.strokeStyle = 'rgba(223, 232, 218, .09)';
    context.setLineDash([2, 5]);
    context.beginPath();
    context.moveTo(left, y);
    context.lineTo(width - right, y);
    context.stroke();
    context.setLineDash([]);
    context.fillStyle = '#93a196';
    context.textAlign = 'right';
    context.fillText(formatPrice(value), width - 12, y);
  }
  context.restore();
}

function drawVolumeGrid(width, left, right, priceBottom, volumeHeight, bottom) {
  const y = priceBottom + 20 + volumeHeight * 0.52;
  context.save();
  context.strokeStyle = 'rgba(223,232,218,.045)';
  context.setLineDash([2, 5]);
  context.beginPath();
  context.moveTo(left, y);
  context.lineTo(width - right, y);
  context.stroke();
  context.restore();
}

function drawTimeLabels(data, width, left, plotRight, plotWidth, y, spacing, endIndex, firstVisibleIndex, lastVisibleIndex) {
  const first = Math.max(0, firstVisibleIndex);
  const last = Math.min(data.length - 1, lastVisibleIndex);
  const candleCount = last - first + 1;
  const labelSpan = Math.max(0, (candleCount - 1) * spacing);
  const count = Math.min(5, candleCount, Math.max(1, Math.floor(labelSpan / 78) + 1));
  if (count <= 0) return;
  context.save();
  context.fillStyle = '#829186';
  context.font = '9px "DM Mono", monospace';
  context.textBaseline = 'middle';
  for (let tick = 0; tick < count; tick += 1) {
    const index = count === 1 ? first : first + Math.round((tick / (count - 1)) * (last - first));
    const bar = data[index];
    const elapsed = bar.start_simulated_seconds + bar.elapsed_simulated_seconds;
    const x = plotRight - (endIndex - index + 0.5) * spacing;
    const align = x <= left + 44 ? 'left' : x >= plotRight - 44 ? 'right' : 'center';
    context.textAlign = align;
    context.fillText(formatMarketTime(elapsed).replace('+', ''), x, y + 12);
  }
  context.restore();
}

function drawPriceTag(x, y, text, isRising) {
  const width = Math.min(73, Math.max(57, text.length * 6.5 + 12));
  const height = 19;
  const top = Math.max(2, Math.min(chartLayout.height - height - 2, y - height / 2));
  context.fillStyle = isRising ? '#337c57' : '#a14f45';
  context.beginPath();
  context.roundRect(x, top, width, height, 3);
  context.fill();
  context.fillStyle = '#f3f8ef';
  context.font = '9px "DM Mono", monospace';
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillText(text, x + width / 2, top + height / 2 + .5, width - 8);
  context.textAlign = 'left';
}

function drawCrosshair(index, mapPrice) {
  const { left, right, plotRight, endIndex, barSpacing, priceBottom, height, bottom, data, width } = chartLayout;
  const centerX = plotRight - (endIndex - index + 0.5) * barSpacing;
  if (centerX < left || centerX > plotRight) return;
  context.save();
  context.strokeStyle = 'rgba(205, 225, 204, .44)';
  context.lineWidth = 1;
  context.setLineDash([3, 4]);
  context.beginPath();
  context.moveTo(centerX, 16);
  context.lineTo(centerX, height - bottom);
  context.stroke();
  context.restore();

  const bar = data[index];
  const start = bar.start_simulated_seconds + bar.elapsed_simulated_seconds;
  const volumeLabel = latestState?.current_bar?.volume_unit || 'units';
  const directionClass = bar.close >= bar.open ? 'tooltip-up' : 'tooltip-down';
  tooltip.innerHTML = `
    <div class="tooltip-title">${latestState?.session ? formatMarketTime(start, true) : `${formatElapsed(start)} elapsed`}</div>
    <div class="tooltip-row"><span>Open</span><strong>${formatPrice(bar.open)}</strong></div>
    <div class="tooltip-row"><span>High</span><strong>${formatPrice(bar.high)}</strong></div>
    <div class="tooltip-row"><span>Low</span><strong>${formatPrice(bar.low)}</strong></div>
    <div class="tooltip-row"><span>Close</span><strong class="${directionClass}">${formatPrice(bar.close)}</strong></div>
    <div class="tooltip-row"><span>Volume</span><strong>${formatVolume(bar.volume)} ${volumeLabel}</strong></div>`;
  tooltip.classList.add('visible');
  tooltip.setAttribute('aria-hidden', 'false');
  const tooltipX = centerX > width * 0.66 ? Math.max(9, centerX - 184) : centerX + 15;
  const closeY = mapPrice(bar.close);
  tooltip.style.left = `${Math.min(width - 183, Math.max(9, tooltipX))}px`;
  tooltip.style.top = `${Math.min(height - 153, Math.max(9, closeY - 38))}px`;
}

function moveChart(event) {
  if (!chartLayout?.data.length) return;
  if (dragState && (event.pointerId === undefined || dragState.pointerId === null || dragState.pointerId === event.pointerId)) {
    const delta = event.clientX - dragState.startX;
    if (Math.abs(delta) > 3) dragState.moved = true;
    if (dragState.moved) {
      rightOffset = clamp(
        dragState.startOffset + delta / barSpacing,
        0,
        chartLayout.data.length - 1,
      );
      followLatest = rightOffset < 0.25;
      hoverIndex = -1;
      tooltip.classList.remove('visible');
      tooltip.setAttribute('aria-hidden', 'true');
      updateLatestButton();
      drawChart();
      return;
    }
  }
  const rect = canvas.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const { left, plotRight, endIndex, barSpacing, data } = chartLayout;
  if (x < left || x > plotRight) {
    hoverIndex = -1;
    tooltip.classList.remove('visible');
    tooltip.setAttribute('aria-hidden', 'true');
    drawChart();
    return;
  }
  const index = Math.round(endIndex - (plotRight - x) / barSpacing + 0.5);
  hoverIndex = index >= 0 && index < data.length ? index : -1;
  if (hoverIndex < 0) {
    tooltip.classList.remove('visible');
    tooltip.setAttribute('aria-hidden', 'true');
  }
  drawChart();
}

canvas.addEventListener('pointermove', moveChart);
canvas.addEventListener('mousemove', moveChart);

function endChartDrag(event) {
  if (!dragState || (event.pointerId !== undefined && dragState.pointerId !== event.pointerId)) return;
  dragState = null;
  canvas.classList.remove('is-panning');
  if (event.pointerId !== undefined && canvas.hasPointerCapture(event.pointerId)) {
    canvas.releasePointerCapture(event.pointerId);
  }
}

canvas.addEventListener('pointerup', endChartDrag);
canvas.addEventListener('pointercancel', endChartDrag);
canvas.addEventListener('mouseup', endChartDrag);
window.addEventListener('mouseup', endChartDrag);
canvas.addEventListener('lostpointercapture', (event) => {
  if (dragState?.pointerId === event.pointerId) {
    dragState = null;
    canvas.classList.remove('is-panning');
  }
});

canvas.addEventListener('pointerleave', () => {
  if (dragState) return;
  hoverIndex = -1;
  tooltip.classList.remove('visible');
  tooltip.setAttribute('aria-hidden', 'true');
  drawChart();
});

window.addEventListener('resize', drawChart);
new ResizeObserver(drawChart).observe(frame);
setInterval(pollState, POLL_INTERVAL_MS);
pollState();
