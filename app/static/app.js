const API_BASE = "";
const POLL_MS = 60000;

const tickerInput = document.getElementById("ticker-input");
const searchBtn = document.getElementById("search-btn");
const latestPriceEl = document.getElementById("latest-price");
const statusMsgEl = document.getElementById("status-msg");
const emptyEl = document.getElementById("chart-empty");
const canvas = document.getElementById("price-chart");
const ctx = canvas.getContext("2d");

let pollTimer = null;
let points = [];
let currentTicker = "";

function setStatus(message, isError = false) {
  statusMsgEl.textContent = message;
  statusMsgEl.style.color = isError ? "#b91c1c" : "var(--accent-dark)";
}

function resizeCanvas() {
  const ratio = window.devicePixelRatio || 1;
  canvas.width = canvas.clientWidth * ratio;
  canvas.height = canvas.clientHeight * ratio;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
}

function drawChart() {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  ctx.clearRect(0, 0, width, height);

  if (!points.length) {
    emptyEl.style.display = "flex";
    return;
  }
  emptyEl.style.display = "none";

  const padding = 36;
  const prices = points.map((p) => p.price);
  let minPrice = Math.min(...prices);
  let maxPrice = Math.max(...prices);
  if (minPrice === maxPrice) {
    minPrice -= 1;
    maxPrice += 1;
  }

  const minTs = points[0].ts;
  const maxTs = points[points.length - 1].ts || minTs + 1;
  const span = maxTs - minTs || 1;

  ctx.lineWidth = 2;
  ctx.strokeStyle = "#d97706";
  ctx.beginPath();

  points.forEach((point, idx) => {
    const x = padding + ((point.ts - minTs) / span) * (width - padding * 2);
    const y =
      height -
      padding -
      ((point.price - minPrice) / (maxPrice - minPrice)) * (height - padding * 2);
    if (idx === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });
  ctx.stroke();

  ctx.strokeStyle = "rgba(31, 26, 23, 0.2)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(padding, padding);
  ctx.lineTo(padding, height - padding);
  ctx.lineTo(width - padding, height - padding);
  ctx.stroke();

  ctx.fillStyle = "#5b4b43";
  ctx.font = "12px 'Space Grotesk', sans-serif";
  ctx.fillText(maxPrice.toFixed(2), padding + 6, padding + 12);
  ctx.fillText(minPrice.toFixed(2), padding + 6, height - padding + 18);
}

async function fetchHistory(ticker) {
  const res = await fetch(`${API_BASE}/api/history/${ticker}`);
  if (!res.ok) {
    throw new Error("Ticker not found");
  }
  const data = await res.json();
  points = data.map((item) => ({ ts: item.ts, price: item.price }));
}

async function fetchLatest(ticker) {
  const res = await fetch(`${API_BASE}/api/latest/${ticker}`);
  if (!res.ok) {
    throw new Error("Ticker not found");
  }
  const data = await res.json();
  const last = points[points.length - 1];
  if (!last || data.ts > last.ts) {
    points.push({ ts: data.ts, price: data.price });
  }
  latestPriceEl.textContent = data.price.toFixed(4);
}

async function handleSearch() {
  const raw = tickerInput.value.trim().toUpperCase();
  if (!raw) {
    setStatus("Enter a ticker symbol.", true);
    return;
  }

  currentTicker = raw;
  setStatus("Loading history...");
  if (pollTimer) {
    clearInterval(pollTimer);
  }

  try {
    await fetchHistory(currentTicker);
    await fetchLatest(currentTicker);
    drawChart();
    setStatus(`Streaming ${currentTicker} every 60 seconds.`);
    pollTimer = setInterval(async () => {
      try {
        await fetchLatest(currentTicker);
        drawChart();
      } catch (err) {
        setStatus("Polling failed. Try searching again.", true);
      }
    }, POLL_MS);
  } catch (err) {
    setStatus("Ticker not found. Try AAPL, MSFT, GOOG, or TSLA.", true);
  }
}

searchBtn.addEventListener("click", handleSearch);
tickerInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    handleSearch();
  }
});

window.addEventListener("resize", () => {
  resizeCanvas();
  drawChart();
});

resizeCanvas();
drawChart();
