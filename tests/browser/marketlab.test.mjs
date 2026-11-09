import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { createServer } from 'node:net';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));
const require = createRequire(import.meta.url);
let playwright;
try { playwright = require('playwright'); } catch {
  playwright = require(process.env.PLAYWRIGHT_MODULE || `${process.env.HOME}/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright`);
}
let server, browser, base;
const prefix = '/price-generator';
before(async () => {
  const reservation = createServer();
  await new Promise((resolve) => reservation.listen(0, '127.0.0.1', resolve));
  const port = reservation.address().port;
  await new Promise((resolve) => reservation.close(resolve));
  server = spawn(`${root}.venv/bin/python`, ['server.py'], { cwd: root, env: { ...process.env, HOST: '127.0.0.1', PORT: String(port), BASE_PATH: prefix, AUTH_SESSION_URL: '' }, stdio: 'ignore' });
  base = `http://127.0.0.1:${port}${prefix}`;
  let ready = false;
  for (let attempt = 0; attempt < 100; attempt++) {
    try { if ((await fetch(`${base}/health`)).ok) { ready = true; break; } } catch {}
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  assert.ok(ready, 'isolated Python server starts');
  browser = await playwright.chromium.launch({ channel: 'chrome', headless: true });
});
after(async () => { await browser?.close(); server?.kill(); });

async function status(page, text) {
  await page.locator('#orderBookStatus').filter({ hasText: text }).waitFor({ timeout: 10000 });
}

test('original Market Lab controls, styling and full-width chart remain with a ready book below', async () => {
  assert.equal(createHash('sha256').update(await readFile(`${root}web/styles.css`)).digest('hex'), 'fae398f1e350c418dead9ec6a5601366cafadc083561dbef043f394afac16c1c');
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  try {
    await page.goto(`${base}/`);
    await page.getByRole('heading', { name: 'Price generator', exact: true }).waitFor();
    assert.deepEqual(await page.getByLabel('Asset class').locator('option').evaluateAll((options) => options.map((option) => option.value)), ['stocks', 'spot_crypto']);
    assert.deepEqual(await page.getByLabel('Simulation model').locator('option').evaluateAll((options) => options.map((option) => option.value)), ['regime_switching', 'mean_reverting', 'jump_diffusion']);
    await page.getByLabel('Bar interval', { exact: true }).waitFor();
    for (const name of ['Zoom out', 'Zoom in', 'Reset', 'Latest']) await page.getByRole('button', { name, exact: true }).waitFor();
    assert.equal(await page.getByRole('textbox').count(), 0);
    assert.doesNotMatch(await page.locator('body').innerText(), /\bticker\b|\bsearch\b/i);
    const style = await page.locator('#chartFrame').evaluate((element) => ({ background: getComputedStyle(element).backgroundColor, borderRadius: getComputedStyle(element).borderRadius }));
    assert.deepEqual(style, { background: 'rgb(18, 36, 31)', borderRadius: '10px' });
    const chart = await page.locator('#chartFrame').boundingBox();
    const main = await page.locator('main').boundingBox();
    assert.ok(Math.abs(chart.width - main.width) <= 1);
    assert.ok(chart.height >= 360);
    assert.equal((await page.locator('.topbar').boundingBox()).height, 76);
    if (process.env.CAPTURE_BASELINE) {
      await page.screenshot({ path: '/tmp/marketlab-before-desktop.png', fullPage: true });
      await page.setViewportSize({ width: 390, height: 844 });
      await page.waitForTimeout(250);
      await page.screenshot({ path: '/tmp/marketlab-before-mobile.png', fullPage: true });
      await page.setViewportSize({ width: 1440, height: 1100 });
    }
    const book = page.getByRole('region', { name: 'Synthetic order book' });
    await book.waitFor({ timeout: 3000 });
    await status(page, 'Ready to start');
    const bookBounds = await book.boundingBox();
    const chartSection = await page.locator('.chart-section').boundingBox();
    assert.ok(bookBounds.y >= chartSection.y + chartSection.height);
  } finally { await page.close(); }
});

test('synthetic model Start/Stop renders depth from the same payload and preserves mobile flow', async () => {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  const page = await context.newPage();
  const endpoints = [];
  page.on('request', (request) => { if (request.url().includes('/api/')) endpoints.push(new URL(request.url()).pathname); });
  await page.route('**/api/**', async (route) => {
    const response = await route.fetch();
    if (response.ok() && response.headers()['content-type']?.includes('json')) {
      const payload = await response.json();
      if (payload.order_book) {
        assert.equal(payload.order_book.reference_price, payload.current_bar.close);
        assert.equal(payload.order_book.run_id, payload.run_id);
      }
    }
    await route.fulfill({ response });
  });
  try {
    await page.goto(`${base}/`);
    await page.getByLabel('Asset class').selectOption('spot_crypto');
    await page.getByLabel('Simulation model').selectOption('mean_reverting');
    await page.getByLabel('Bar interval', { exact: true }).selectOption('2m');
    await page.getByRole('button', { name: 'Start stream', exact: true }).click();
    await status(page, 'Running');
    assert.equal(await page.locator('[data-book-side="ask"]').count(), 10);
    assert.equal(await page.locator('[data-book-side="bid"]').count(), 10);
    await page.waitForFunction(() => document.querySelector('#orderBookReference')?.textContent === document.querySelector('#lastPrice')?.textContent);
    const askPrices = await page.locator('[data-book-side="ask"] .book-price').allTextContents();
    const bidPrices = await page.locator('[data-book-side="bid"] .book-price').allTextContents();
    const number = (text) => Number(text.replaceAll(',', ''));
    assert.ok(number(askPrices[0]) > number(askPrices[9]));
    assert.ok(number(bidPrices[0]) > number(bidPrices[9]));
    await page.getByRole('button', { name: 'Stop stream', exact: true }).click();
    await status(page, 'Stopped');
    assert.equal(await page.locator('[data-book-side="ask"]').count(), 10);
    const stopped = await page.locator('#orderBookLevels').innerText();
    await page.waitForTimeout(1300);
    assert.equal(await page.locator('#orderBookLevels').innerText(), stopped);
    await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
    await page.getByRole('button', { name: 'Zoom out', exact: true }).click();
    await page.getByRole('button', { name: 'Reset', exact: true }).click();
    await page.getByRole('button', { name: 'Latest', exact: true }).click();
    assert.equal(await page.getByRole('button', { name: 'Latest', exact: true }).getAttribute('aria-pressed'), 'true');
    await page.screenshot({ path: '/tmp/marketlab-after-desktop.png', fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(250);
    const book = await page.getByRole('region', { name: 'Synthetic order book' }).boundingBox();
    const chart = await page.locator('.chart-section').boundingBox();
    assert.ok(book.y >= chart.y + chart.height);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: '/tmp/marketlab-after-mobile.png', fullPage: true });
    assert.ok(endpoints.every((path) => /^\/price-generator\/api\/(state|start|stop)$/.test(path)));
  } finally {
    await page.unrouteAll({ behavior: 'wait' });
    await context.close();
  }
});

test('existing state polling marks book unavailable on errors and recovers on the next successful poll', async () => {
  const page = await browser.newPage();
  let unavailable = false;
  let polls = 0;
  await page.route('**/api/state*', async (route) => {
    polls++;
    if (unavailable) return route.fulfill({ status: 503, json: { error: 'Test service interruption' } });
    return route.continue();
  });
  try {
    await page.goto(`${base}/`);
    await page.getByRole('button', { name: 'Start stream', exact: true }).click();
    await status(page, 'Running');
    unavailable = true;
    await status(page, 'Unavailable');
    assert.equal(await page.locator('[data-book-side="bid"]').count(), 10);
    await page.getByRole('alert').filter({ hasText: 'Test service interruption' }).waitFor();
    const priorPolls = polls;
    unavailable = false;
    await status(page, 'Running');
    assert.ok(polls > priorPolls);
    await page.getByRole('alert').waitFor({ state: 'hidden' });
    await page.getByRole('button', { name: 'Stop stream', exact: true }).click();
    await status(page, 'Stopped');
  } finally { await page.close(); }
});

test('tiny-price public state retains ten distinct levels and a nonzero spread', async () => {
  const response = await fetch(`${base}/api/start`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ asset_class: 'stocks', bar_interval: '1m', simulation_model: 'mean_reverting' }) });
  const state = await response.json();
  const reference = 1e-9;
  const tick = 1e-11;
  state.running = false;
  state.start_price = reference;
  state.current_bar = { ...state.current_bar, open: reference, high: reference, low: reference, close: reference };
  state.order_book = { run_id: state.run_id, sequence: 1, ts: Date.now() / 1000, reference_price: reference, reference_simulated_seconds: 0, status: 'stopped', tick_size: tick,
    bids: Array.from({ length: 10 }, (_, i) => ({ price: reference - (i + 1) * tick, quantity: 100, cumulative_quantity: (i + 1) * 100 })),
    asks: Array.from({ length: 10 }, (_, i) => ({ price: reference + (i + 1) * tick, quantity: 100, cumulative_quantity: (i + 1) * 100 })),
  };
  const page = await browser.newPage();
  await page.route('**/api/state*', (route) => route.fulfill({ json: state }));
  try {
    await page.goto(`${base}/`);
    await status(page, 'Stopped');
    for (const side of ['ask', 'bid']) {
      const prices = await page.locator(`[data-book-side="${side}"] .book-price`).allTextContents();
      assert.equal(new Set(prices).size, 10, `${side} levels remain distinct`);
      assert.ok(prices.every((price) => Number(price.replaceAll(',', '')) > 0));
    }
    assert.ok(Number(await page.locator('#orderBookSpread').innerText()) > 0, 'spread remains positive');
  } finally { await page.close(); }
});

test('US stock controls close the session, survive reload, and fit a mobile screen', async () => {
  await fetch(`${base}/api/stop`, { method: 'POST', body: '{}' });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  try {
    await page.goto(`${base}/`);
    await page.getByLabel('Asset class').selectOption('stocks');
    await page.getByLabel('US stock session', { exact: true }).selectOption('final_minute');
    await page.getByLabel('Playback speed').selectOption('120');
    await page.getByLabel('Bar interval', { exact: true }).selectOption('4h');
    await page.getByRole('button', { name: 'Start stream', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('#marketPhase').textContent === 'Market closed');
    assert.equal(await page.locator('#marketClock').innerText(), '16:00:00 ET');
    assert.match(await page.locator('#auctionSummary').innerText(), /Closing auction/);
    assert.match(await page.locator('#auctionSummary').innerText(), /shares/);
    assert.match(await page.locator('#chartSubtitle').innerText(), /ET/);
    assert.equal(await page.locator('#visibleCount').innerText(), '1 candles');
    assert.equal(await page.getByLabel('Playback speed').isEnabled(), true);
    await page.reload();
    await page.waitForFunction(() => document.querySelector('#marketPhase').textContent === 'Market closed');
    assert.equal(await page.getByLabel('US stock session', { exact: true }).inputValue(), 'final_minute');
    assert.equal(await page.getByLabel('Playback speed').inputValue(), '120');
    await page.getByLabel('US stock session', { exact: true }).selectOption('opening');
    await page.getByLabel('Playback speed').selectOption('20');
    await page.getByLabel('Bar interval', { exact: true }).selectOption('1m');
    await page.getByRole('button', { name: 'Start stream', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('#marketPhase').textContent === 'Opening discovery');
    assert.equal(await page.getByLabel('US stock session', { exact: true }).isDisabled(), true);
    await page.screenshot({ path: '/tmp/stock-session-desktop.png', fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(250);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: '/tmp/stock-session-mobile.png', fullPage: true });
    await page.getByRole('button', { name: 'Stop stream', exact: true }).click();
    await status(page, 'Stopped');
    const clock = await page.locator('#marketClock').innerText();
    await page.waitForTimeout(300);
    assert.equal(await page.locator('#marketClock').innerText(), clock);
    await page.getByLabel('Asset class').selectOption('spot_crypto');
    assert.equal(await page.locator('#stockSession').isVisible(), false);
    await page.getByRole('button', { name: 'Start stream', exact: true }).click();
    await status(page, 'Running');
    assert.match(await page.locator('#chartSubtitle').innerText(), /elapsed/);
    await page.getByRole('button', { name: 'Stop stream', exact: true }).click();
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('an old delayed poll cannot overwrite a stopped stock session', async () => {
  await fetch(`${base}/api/stop`, { method: 'POST', body: '{}' });
  const page = await browser.newPage();
  let releaseOld, releaseFresh, captured;
  const oldGate = new Promise((resolve) => { releaseOld = resolve; });
  const freshGate = new Promise((resolve) => { releaseFresh = resolve; });
  const capture = new Promise((resolve) => { captured = resolve; });
  let first = true;
  try {
    await page.goto(`${base}/`);
    await page.getByLabel('Asset class').selectOption('stocks');
    await page.getByLabel('US stock session', { exact: true }).selectOption('midday');
    await page.getByLabel('Playback speed').selectOption('600');
    await page.getByLabel('Bar interval', { exact: true }).selectOption('1m');
    await page.getByRole('button', { name: 'Start stream', exact: true }).click();
    await status(page, 'Running');
    await page.route('**/api/state*', async (route) => {
      if (!first) { await freshGate; return route.continue(); }
      first = false;
      const response = await route.fetch();
      const payload = await response.json();
      assert.equal(payload.running, true);
      captured();
      await oldGate;
      await route.fulfill({ json: payload });
    });
    await capture;
    await page.getByRole('button', { name: 'Stop stream', exact: true }).click();
    await status(page, 'Stopped');
    const clock = await page.locator('#marketClock').innerText();
    const oldResponse = page.waitForResponse((response) => response.url().includes('/api/state'));
    releaseOld();
    await oldResponse;
    await page.waitForTimeout(100);
    assert.match(await page.locator('#orderBookStatus').innerText(), /^Stopped/);
    assert.equal(await page.locator('#marketClock').innerText(), clock);
    const state = await (await page.request.get(`${base}/api/state?history=1`)).json();
    assert.equal(await page.locator('#visibleCount').innerText(), `${state.history.length + 1} candles`);
  } finally {
    releaseOld(); releaseFresh();
    await page.unrouteAll({ behavior: 'wait' });
    await page.close();
  }
});

test('a poll overtaken by Start recovers candles from the new stock run', async () => {
  await fetch(`${base}/api/stop`, { method: 'POST', body: '{}' });
  const page = await browser.newPage();
  let releaseOld, captured;
  const gate = new Promise((resolve) => { releaseOld = resolve; });
  const capture = new Promise((resolve) => { captured = resolve; });
  let first = true;
  const freshUrls = [];
  try {
    await page.goto(`${base}/`);
    await page.getByLabel('Asset class').selectOption('stocks');
    await page.getByLabel('US stock session', { exact: true }).selectOption('midday');
    await page.getByLabel('Playback speed').selectOption('600');
    await page.getByLabel('Bar interval', { exact: true }).selectOption('1m');
    await page.getByRole('button', { name: 'Start stream', exact: true }).click();
    await status(page, 'Running');
    await page.route('**/api/state*', async (route) => {
      if (!first) { freshUrls.push(route.request().url()); return route.continue(); }
      first = false;
      captured();
      // This old request reaches the service only after a new run has begun.
      await gate;
      const response = await route.fetch();
      await route.fulfill({ response });
    });
    await capture;
    await page.getByRole('button', { name: 'Stop stream', exact: true }).click();
    await status(page, 'Stopped');
    await page.getByLabel('US stock session', { exact: true }).selectOption('closing');
    await page.getByRole('button', { name: 'Start stream', exact: true }).click();
    await status(page, 'Running');
    await page.waitForTimeout(150);
    const oldResponse = page.waitForResponse((response) => response.url().includes('/api/state'));
    releaseOld();
    await oldResponse;
    await page.waitForTimeout(350);
    assert.ok(freshUrls.some((url) => new URL(url).searchParams.get('history') === '1'), 'the next fresh poll recovers consumed candles');
    assert.equal(await page.getByLabel('US stock session', { exact: true }).inputValue(), 'closing');
    await page.getByRole('button', { name: 'Stop stream', exact: true }).click();
    await status(page, 'Stopped');
  } finally {
    releaseOld();
    await page.unrouteAll({ behavior: 'wait' });
    await page.close();
  }
});
