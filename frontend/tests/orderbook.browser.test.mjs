import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require('playwright'); } catch {
  playwright = require(process.env.PLAYWRIGHT_MODULE || `${process.env.HOME}/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright`);
}
const base = process.env.FRONTEND_URL || 'http://127.0.0.1:4200';
let browser;
before(async () => { browser = await playwright.chromium.launch({ channel: 'chrome', headless: true }); });
after(async () => { await browser?.close(); });

const snapshot = (ticker = 'AAPL', sequence = 1, status = 'open', reference = 100) => ({
  ticker, sequence, ts: 1793458800 + sequence, reference_ts: 1793458800,
  reference_price: reference, session_status: status,
  bids: Array.from({ length: 10 }, (_, i) => ({ price: reference - (i + 1) * .01, quantity: (i + 1) * 100, cumulative_quantity: (i + 1) * (i + 2) * 50 })),
  asks: Array.from({ length: 10 }, (_, i) => ({ price: reference + (i + 1) * .01, quantity: (i + 1) * 200, cumulative_quantity: (i + 1) * (i + 2) * 100 })),
});

async function search(page, ticker) {
  await page.getByLabel('Ticker', { exact: true }).fill(ticker);
  await page.getByRole('button', { name: 'Search', exact: true }).click();
}

async function waitText(locator, text) {
  await locator.filter({ hasText: text }).waitFor({ timeout: 10000 });
}

async function controlledPage({ stream = 'abort', status = 'open', slow = false, initialSequence = 1, streamReference = 100, streamReferenceTs = 1793458800, configTime = '2026-10-30T11:00:00-04:00' } = {}) {
  const context = await browser.newContext({ timezoneId: 'Asia/Tokyo' });
  const page = await context.newPage();
  const posts = [];
  const historyRequests = [];
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const parts = url.pathname.split('/');
    const ticker = parts[3];
    const cors = { 'access-control-allow-origin': '*', 'access-control-allow-headers': 'content-type', 'access-control-allow-methods': 'GET,POST,OPTIONS' };
    if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers: cors });
    if (ticker === 'INVALID') return route.fulfill({ status: 404, headers: cors, body: '{}' });
    if (ticker === 'AAPL' && slow) await new Promise((resolve) => setTimeout(resolve, 1200));
    if (parts[2] === 'config') return route.fulfill({ json: { simulation_cur_dt_iso: configTime, server_now_epoch: Date.now() / 1000 }, headers: cors });
    if (parts[2] === 'history') {
      historyRequests.push(ticker);
      return route.fulfill({ json: [{ ts: 1793458740, price: 99 }], headers: cors });
    }
    if (parts[2] === 'params') {
      if (route.request().method() === 'POST') posts.push(ticker);
      return route.fulfill({ json: { volatility: .2, drift: .05 }, headers: cors });
    }
    if (parts[2] === 'orderbook' && parts[4] === 'stream') {
      if (stream === 'abort') return route.abort();
      return route.fulfill({ headers: { ...cors, 'content-type': 'text/event-stream' }, body: `data: ${JSON.stringify({ ...snapshot(ticker, 2, status, ticker === 'MSFT' ? 200 : streamReference), reference_ts: streamReferenceTs })}\n\n` });
    }
    if (parts[2] === 'orderbook') return route.fulfill({ json: snapshot(ticker, initialSequence, status, ticker === 'MSFT' ? 200 : 100), headers: cors });
    return route.abort();
  });
  await page.goto(base);
  return { context, page, posts, historyRequests };
}

test('live API renders two sides, live updates, New York labels and desktop/mobile layout', async () => {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  const page = await context.newPage();
  try {
    await page.goto(base);
    await search(page, 'AAPL');
    const book = page.getByRole('region', { name: 'Live order book' });
    await book.waitFor();
    await page.locator('[data-side="ask"]').first().waitFor();
    assert.equal(await page.locator('[data-side="ask"]').count(), 10);
    assert.equal(await page.locator('[data-side="bid"]').count(), 10);
    const asks = await page.locator('[data-side="ask"] .level-price').allTextContents();
    const bids = await page.locator('[data-side="bid"] .level-price').allTextContents();
    assert.ok(Number(asks[0]) > Number(asks[9]));
    assert.ok(Number(bids[0]) > Number(bids[9]));
    await waitText(book, 'Cumulative');
    await waitText(book, 'Spread');
    await waitText(page.locator('.badge'), 'New York');
    const firstSnapshotTime = (await book.locator('.book-footnote').textContent()).trim();
    await page.waitForFunction((previous) => document.querySelector('.book-footnote')?.textContent?.trim() !== previous, firstSnapshotTime, { timeout: 4000 });
    assert.equal(await book.locator('.reference-row strong').first().innerText(), await page.locator('.status .stat-block .value').first().innerText());
    const chart = await page.locator('.chart-wrap').boundingBox();
    const desktopBook = await book.boundingBox();
    assert.ok(desktopBook.x >= chart.x + chart.width - 1);
    await page.setViewportSize({ width: 390, height: 844 });
    const mobileChart = await page.locator('.chart-wrap').boundingBox();
    const mobileBook = await book.boundingBox();
    assert.ok(mobileBook.y >= mobileChart.y + mobileChart.height);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  } finally { await context.close(); }
});

test('loading, reconnecting then stale retain the last received levels', async () => {
  const { context, page } = await controlledPage({ slow: true });
  try {
    await search(page, 'AAPL');
    const book = page.getByRole('region', { name: 'Live order book' });
    await waitText(book, 'Loading');
    await waitText(book, 'Reconnecting');
    await page.locator('[data-side="bid"]').first().waitFor();
    await waitText(book, 'Stale');
    assert.equal(await page.locator('[data-side="bid"]').count(), 10);
    await page.waitForTimeout(1200);
    await waitText(book, 'Stale');
  } finally { await context.close(); }
});

test('closed snapshot is labeled closed and is not stale', async () => {
  const { context, page } = await controlledPage({ status: 'closed' });
  try {
    await search(page, 'AAPL');
    const book = page.getByRole('region', { name: 'Live order book' });
    await waitText(book, 'Market closed');
    await page.waitForTimeout(5500);
    assert.ok(!(await book.textContent()).includes('Stale'));
  } finally { await context.close(); }
});

test('initial frozen closed snapshot preserves the later configured simulation clock', async () => {
  const { context, page } = await controlledPage({ status: 'closed', configTime: '2026-10-31T17:30:00-04:00' });
  try {
    await waitText(page.locator('.badge'), '05:30:');
    await search(page, 'AAPL');
    await waitText(page.getByRole('region', { name: 'Live order book' }), 'Market closed');
    assert.match(await page.locator('.badge strong').innerText(), /05:30:.*PM/);
  } finally { await context.close(); }
});

test('stream connection accepts a fresh full snapshot after sequence resets', async () => {
  const { context, page } = await controlledPage({ stream: 'message', initialSequence: 100, streamReference: 101 });
  try {
    await search(page, 'AAPL');
    await waitText(page.locator('.reference-row'), '101.0000');
    await waitText(page.locator('.status .stat-block').first(), '101.0000');
    await page.getByRole('img', { name: /Price history chart.*latest 101.0000/ }).waitFor();
  } finally { await context.close(); }
});

test('backward reference time reloads history and keeps chart aligned with the snapshot', async () => {
  const { context, page, historyRequests } = await controlledPage({ stream: 'message', initialSequence: 100, streamReference: 101, streamReferenceTs: 1793458680 });
  try {
    await search(page, 'AAPL');
    await page.getByRole('img', { name: /Price history chart.*latest 101.0000/ }).waitFor({ timeout: 10000 });
    assert.ok(historyRequests.length >= 2);
  } finally { await context.close(); }
});

test('reconnecting and stale notices do not rewind the simulation clock', async () => {
  const { context, page } = await controlledPage();
  try {
    await search(page, 'AAPL');
    await page.locator('[data-side="bid"]').first().waitFor();
    const seconds = (text) => {
      const match = text.match(/(\d+):(\d+):(\d+)/);
      return Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]);
    };
    const start = seconds(await page.locator('.badge strong').innerText());
    await page.waitForTimeout(6500);
    const end = seconds(await page.locator('.badge strong').innerText());
    assert.ok((end - start + 86400) % 86400 >= 5, 'clock continues through status-only updates');
  } finally { await context.close(); }
});

test('replayed frozen snapshot after reconnect does not rewind the closed-session clock', async () => {
  const { context, page } = await controlledPage({ stream: 'message', status: 'closed' });
  try {
    await search(page, 'AAPL');
    await page.locator('[data-side="bid"]').first().waitFor();
    await page.waitForTimeout(1000);
    const clock = page.locator('.badge strong');
    const seconds = (text) => {
      const match = text.match(/(\d+):(\d+):(\d+)/);
      return Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]);
    };
    const start = seconds(await clock.innerText());
    await page.waitForTimeout(6500);
    const end = seconds(await clock.innerText());
    assert.ok((end - start + 86400) % 86400 >= 5, 'clock advances through identical reconnect snapshots');
  } finally { await context.close(); }
});

test('new ticker wins over slow search and parameter changes use selected symbol', async () => {
  const { context, page, posts } = await controlledPage({ slow: true, stream: 'message' });
  try {
    await search(page, 'AAPL');
    await search(page, 'MSFT');
    const book = page.getByRole('region', { name: 'Live order book' });
    await waitText(book, 'MSFT');
    await page.waitForTimeout(1500);
    assert.ok(!(await book.textContent()).includes('AAPL'));
    await page.getByLabel('Ticker', { exact: true }).fill('TSLA');
    await page.getByRole('button', { name: 'Update', exact: true }).click();
    await page.waitForTimeout(200);
    assert.deepEqual(posts, ['MSFT']);
    await search(page, 'INVALID');
    await waitText(book, 'Unavailable');
    assert.equal(await page.locator('[data-side="bid"]').count(), 0);
  } finally { await context.close(); }
});
