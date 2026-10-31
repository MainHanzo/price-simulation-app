import { CommonModule } from '@angular/common';
import {
  AfterViewInit,
  Component,
  ElementRef,
  HostListener,
  OnDestroy,
  ViewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Chart } from 'chart.js/auto';
import { Subscription } from 'rxjs';
import { OrderBook } from './order-book';
import { OrderBookService } from './order-book.service';
import { OrderBookSnapshot, OrderBookState } from './order-book.types';

type PricePoint = {
  ts: number;
  price: number;
};

@Component({
  selector: 'app-root',
  imports: [CommonModule, FormsModule, OrderBook],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App implements AfterViewInit, OnDestroy {
  apiBase = 'http://127.0.0.1:8000';
  ticker = '';
  selectedTicker = '';
  bookState: OrderBookState = { ticker: '', status: 'idle', snapshot: null };
  private bookSubscription: Subscription;
  private searchGeneration = 0;
  private searchAbort: AbortController | null = null;
  private clockFromSnapshot = false;
  private lastAppliedSnapshot: OrderBookSnapshot | null = null;
  simulationDtIso = '';
  latestPrice = '--';
  latestTime = '--';
  currentFrontDisplay = '--';
  statusMsg = '';
  isError = false;
  volatility = '';
  drift = '';
  paramsReady = false;
  overlayPos = { x: 14, y: 14 };
  overlaySize = { width: 200, height: 160 };
  private isDraggingOverlay = false;
  private overlayDragOffset = { x: 0, y: 0 };
  points: PricePoint[] = [];
  showEmpty = true;

  private chart: Chart | null = null;
  private clockTimer: number | null = null;
  private simulationBase: Date | null = null;
  private simulationStartMs: number | null = null;

  constructor(private readonly orderBooks: OrderBookService) {
    this.bookSubscription = orderBooks.state$.subscribe((state) => {
      this.bookState = state;
      if (state.snapshot && state.snapshot !== this.lastAppliedSnapshot) {
        const previous = this.lastAppliedSnapshot;
        this.lastAppliedSnapshot = state.snapshot;
        const sameSnapshot = previous?.ticker === state.snapshot.ticker && previous.sequence === state.snapshot.sequence
          && previous.ts === state.snapshot.ts && previous.reference_ts === state.snapshot.reference_ts
          && previous.reference_price === state.snapshot.reference_price;
        this.applySnapshot(state.snapshot, !sameSnapshot);
        if (previous?.ticker === state.snapshot.ticker && (state.snapshot.sequence < previous.sequence || state.snapshot.reference_ts < previous.reference_ts)) {
          void this.reloadHistory(state.snapshot.ticker);
          if (state.snapshot.session_status === 'closed') void this.loadSimulationDt(true);
        }
      }
    });
  }

  @ViewChild('priceChart', { static: true })
  canvasRef!: ElementRef<HTMLCanvasElement>;

  @HostListener('window:resize')
  onResize() {
    if (this.chart) {
      this.chart.resize();
    }
  }

  ngAfterViewInit(): void {
    this.initChart();
    this.loadSimulationDt().finally(() => this.startClock());
  }

  ngOnDestroy(): void {
    this.searchAbort?.abort();
    this.bookSubscription.unsubscribe();
    this.orderBooks.disconnect();
    if (this.clockTimer) {
      window.clearInterval(this.clockTimer);
    }
    if (this.chart) {
      this.chart.destroy();
    }
  }

  async handleSearch(): Promise<void> {
    const raw = this.ticker.trim().toUpperCase();
    if (!raw) {
      this.setStatus('Enter a ticker symbol.', true);
      return;
    }
    this.ticker = raw;
    this.selectedTicker = raw;
    const generation = ++this.searchGeneration;
    this.searchAbort?.abort();
    const controller = new AbortController();
    this.searchAbort = controller;
    this.points = [];
    this.paramsReady = false;
    this.latestPrice = '--';
    this.latestTime = '--';
    this.updateChart();
    this.setStatus('Loading history...', false);
    void this.orderBooks.select(raw);
    try {
      const [historyResponse, paramsResponse] = await Promise.all([
        fetch(`${this.apiBase}/api/history/${encodeURIComponent(raw)}`, { signal: controller.signal }),
        fetch(`${this.apiBase}/api/params/${encodeURIComponent(raw)}`, { signal: controller.signal }),
      ]);
      if (!historyResponse.ok || !paramsResponse.ok) throw new Error('Ticker unavailable');
      const [history, params] = await Promise.all([
        historyResponse.json() as Promise<PricePoint[]>,
        paramsResponse.json() as Promise<{ volatility: number; drift: number }>,
      ]);
      if (generation !== this.searchGeneration) return;
      this.points = history.map(({ ts, price }) => ({ ts, price }));
      this.volatility = params.volatility.toString();
      this.drift = params.drift.toString();
      this.paramsReady = true;
      if (this.bookState.snapshot) this.applySnapshot(this.bookState.snapshot, false);
      else this.setLatestFromPoints();
      this.updateChart();
      this.setStatus(`Showing ${raw} · simulated prices and liquidity.`, false);
    } catch {
      if (generation !== this.searchGeneration) return;
      this.setStatus('Ticker not found. Try AAPL, MSFT, GOOG, or TSLA.', true);
    }
  }

  private applySnapshot(snapshot: OrderBookSnapshot, syncClock = true): void {
    if (snapshot.ticker !== this.selectedTicker) return;
    this.latestPrice = snapshot.reference_price.toFixed(4);
    this.latestTime = this.formatTime(new Date(snapshot.reference_ts * 1000));
    this.points = this.points.filter((point) => point.ts <= snapshot.reference_ts);
    const minute = Math.floor(snapshot.reference_ts / 60);
    const sameMinute = this.points.findIndex((point) => Math.floor(point.ts / 60) === minute);
    if (sameMinute >= 0) {
      this.points[sameMinute] = { ts: snapshot.reference_ts, price: snapshot.reference_price };
    } else {
      this.points.push({ ts: snapshot.reference_ts, price: snapshot.reference_price });
    }
    this.updateChart();
    if (syncClock && snapshot.session_status === 'open') {
      this.clockFromSnapshot = true;
      this.simulationBase = new Date(snapshot.ts * 1000);
      this.simulationStartMs = Date.now();
      this.currentFrontDisplay = this.formatTime(this.simulationBase);
    }
  }

  private async reloadHistory(ticker: string): Promise<void> {
    const generation = this.searchGeneration;
    try {
      const response = await fetch(`${this.apiBase}/api/history/${encodeURIComponent(ticker)}`, { signal: this.searchAbort?.signal });
      if (!response.ok) return;
      const history = await response.json() as PricePoint[];
      if (generation !== this.searchGeneration || ticker !== this.selectedTicker) return;
      this.points = history.map(({ ts, price }) => ({ ts, price }));
      if (this.bookState.snapshot) this.applySnapshot(this.bookState.snapshot, false);
    } catch { /* Retain the reference-aligned chart while a restarted API recovers. */ }
  }

  get chartDescription(): string {
    const last = this.points[this.points.length - 1];
    return `Price history chart for ${this.selectedTicker || 'no symbol'}, ${this.points.length} minute points${last ? `, latest ${last.price.toFixed(4)}` : ''}`;
  }

  private formatTime(date: Date): string {
    return date.toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  private setStatus(message: string, isError: boolean): void {
    this.statusMsg = message;
    this.isError = isError;
  }

  async updateParams(): Promise<void> {
    const selected = this.selectedTicker;
    const generation = this.searchGeneration;
    if (!selected || !this.paramsReady) return;
    try {
      const res = await fetch(`${this.apiBase}/api/params/${encodeURIComponent(selected)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ volatility: this.volatility, drift: this.drift }),
      });
      if (!res.ok) throw new Error('Params unavailable');
      const data = await res.json() as { volatility: number; drift: number };
      if (generation !== this.searchGeneration) return;
      this.volatility = data.volatility.toString();
      this.drift = data.drift.toString();
      this.setStatus(`Params updated for ${selected}.`, false);
    } catch {
      if (generation === this.searchGeneration) this.setStatus('Failed to update params.', true);
    }
  }

  private setLatestFromPoints(): void {
    const last = this.points[this.points.length - 1];
    if (!last) {
      this.latestPrice = '--';
      this.latestTime = '--';
      return;
    }
    this.latestPrice = last.price.toFixed(4);
    this.latestTime = this.formatTime(new Date(last.ts * 1000));
  }

  private getSimulationCurDt(): Date {
    if (this.simulationBase && this.simulationStartMs !== null) {
      const elapsed = Date.now() - this.simulationStartMs;
      return new Date(this.simulationBase.getTime() + elapsed);
    }
    return new Date();
  }

  private startClock(): void {
    if (this.clockTimer) {
      return;
    }
    const update = () => {
      const now = this.getSimulationCurDt();
      this.currentFrontDisplay = this.formatTime(now);
    };
    update();
    this.clockTimer = window.setInterval(update, 1000);
  }

  startOverlayDrag(event: MouseEvent): void {
    const rect = this.canvasRef.nativeElement.getBoundingClientRect();
    this.isDraggingOverlay = true;
    this.overlayDragOffset = {
      x: event.clientX - rect.left - this.overlayPos.x,
      y: event.clientY - rect.top - this.overlayPos.y,
    };
  }

  stopOverlayDrag(): void {
    this.isDraggingOverlay = false;
  }

  onOverlayDrag(event: MouseEvent): void {
    if (!this.isDraggingOverlay) {
      return;
    }
    const rect = this.canvasRef.nativeElement.getBoundingClientRect();
    const nextX = event.clientX - rect.left - this.overlayDragOffset.x;
    const nextY = event.clientY - rect.top - this.overlayDragOffset.y;
    const maxX = Math.max(0, rect.width - this.overlaySize.width);
    const maxY = Math.max(0, rect.height - this.overlaySize.height);
    this.overlayPos = {
      x: Math.min(Math.max(0, nextX), maxX),
      y: Math.min(Math.max(0, nextY), maxY),
    };
  }

  @HostListener('window:mousemove', ['$event'])
  onWindowMouseMove(event: MouseEvent): void {
    this.onOverlayDrag(event);
  }

  @HostListener('window:mouseup')
  onWindowMouseUp(): void {
    this.stopOverlayDrag();
  }

  private async loadSimulationDt(force = false): Promise<void> {
    try {
      const res = await fetch(`${this.apiBase}/api/config`);
      if (!res.ok) {
        return;
      }
      const data = (await res.json()) as {
        simulation_cur_dt_iso?: string;
        server_now_epoch?: number;
      };
      if (data.simulation_cur_dt_iso && typeof data.server_now_epoch === 'number') {
        const parsed = new Date(data.simulation_cur_dt_iso);
        if (!Number.isNaN(parsed.getTime()) && (!this.clockFromSnapshot || force)) {
          const serverNowMs = data.server_now_epoch * 1000;
          const clientNowMs = Date.now();
          const baseMs = parsed.getTime() + (clientNowMs - serverNowMs);
          this.simulationDtIso = data.simulation_cur_dt_iso;
          this.simulationBase = new Date(baseMs);
          this.simulationStartMs = clientNowMs;
        }
      }
    } catch {
      return;
    }
  }

  private initChart(): void {
    const canvas = this.canvasRef.nativeElement;
    this.chart = new Chart(canvas, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          {
            label: 'Price',
            data: [],
            borderColor: '#d97706',
            backgroundColor: 'rgba(217, 119, 6, 0.12)',
            pointRadius: 0,
            tension: 0.25,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'nearest',
          intersect: false,
        },
        scales: {
          x: {
            grid: {
              color: 'rgba(31, 26, 23, 0.2)',
            },
            ticks: {
              maxTicksLimit: 6,
            },
          },
          y: {
            grid: {
              color: 'rgba(31, 26, 23, 0.2)',
            },
          },
        },
        plugins: {
          legend: {
            display: false,
          },
          tooltip: {
            callbacks: {
              title: (items) => {
                const idx = items[0]?.dataIndex ?? 0;
                const point = this.points[idx];
                if (!point) {
                  return '';
                }
                return this.formatTime(new Date(point.ts * 1000)) + ' New York';
              },
              label: (item) => `Price: ${item.formattedValue}`,
            },
          },
        },
      },
    });
  }

  private updateChart(): void {
    this.showEmpty = this.points.length === 0;
    if (!this.chart) {
      return;
    }
    this.chart.data.labels = this.points.map((p) =>
      this.formatTime(new Date(p.ts * 1000))
    );
    this.chart.data.datasets[0].data = this.points.map((p) => p.price);
    this.chart.update('none');
  }
}
