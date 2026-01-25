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
import { io, Socket } from 'socket.io-client';

type PricePoint = {
  ts: number;
  price: number;
};

@Component({
  selector: 'app-root',
  imports: [CommonModule, FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App implements AfterViewInit, OnDestroy {
  apiBase = 'http://127.0.0.1:8000';
  ticker = '';
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
  private socket: Socket | null = null;
  private socketTicker: string | null = null;

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
    if (this.clockTimer) {
      window.clearInterval(this.clockTimer);
    }
    if (this.chart) {
      this.chart.destroy();
    }
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
    }
  }

  async handleSearch(): Promise<void> {
    const raw = this.ticker.trim().toUpperCase();
    if (!raw) {
      this.setStatus('Enter a ticker symbol.', true);
      return;
    }

    this.ticker = raw;
    this.setStatus('Loading history...', false);

    this.cleanupSocketSubscription();

    try {
      const simulationNow = this.getSimulationCurDt();
      const inSession = this.isMarketOpen(simulationNow);
      await this.fetchHistory(raw);
      await this.fetchParams(raw);
      if (inSession) {
        await this.connectSocket(raw);
      }
      this.updateChart();
      if (inSession) {
        this.setStatus(`Streaming ${raw} live.`, false);
      } else {
        this.setStatus('Market closed — history only.', false);
      }
    } catch {
      this.setStatus('Ticker not found. Try AAPL, MSFT, GOOG, or TSLA.', true);
    }
  }

  private setStatus(message: string, isError: boolean): void {
    this.statusMsg = message;
    this.isError = isError;
  }

  private async fetchHistory(ticker: string): Promise<void> {
    const res = await fetch(`${this.apiBase}/api/history/${ticker}`);
    if (!res.ok) {
      throw new Error('Ticker not found');
    }
    const data = (await res.json()) as PricePoint[];
    this.points = data.map((item) => ({ ts: item.ts, price: item.price }));
    this.setLatestFromPoints();
  }

  private async fetchParams(ticker: string): Promise<void> {
    const res = await fetch(`${this.apiBase}/api/params/${ticker}`);
    if (!res.ok) {
      throw new Error('Params unavailable');
    }
    const data = (await res.json()) as { volatility: number; drift: number };
    this.volatility = data.volatility.toString();
    this.drift = data.drift.toString();
    this.paramsReady = true;
  }

  async updateParams(): Promise<void> {
    if (!this.ticker) {
      return;
    }
    const res = await fetch(`${this.apiBase}/api/params/${this.ticker}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        volatility: this.volatility,
        drift: this.drift,
      }),
    });
    if (!res.ok) {
      this.setStatus('Failed to update params.', true);
      return;
    }
    const data = (await res.json()) as { volatility: number; drift: number };
    this.volatility = data.volatility.toString();
    this.drift = data.drift.toString();
    this.setStatus('Params updated.', false);
  }

  private setLatestFromPoints(): void {
    const last = this.points[this.points.length - 1];
    if (!last) {
      this.latestPrice = '--';
      this.latestTime = '--';
      return;
    }
    this.latestPrice = last.price.toFixed(4);
    this.latestTime = new Date(last.ts * 1000).toLocaleTimeString();
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
      this.currentFrontDisplay = now.toLocaleTimeString();
    };
    update();
    this.clockTimer = window.setInterval(update, 1000);
  }

  private setupSocket(): void {
    if (this.socket) {
      return;
    }
    this.socket = io(this.apiBase, {
      transports: ['websocket'],
    });
    this.socket.on('price_update', (payload: { ticker: string; ts: number; price: number }) => {
      if (!payload || payload.ticker !== this.ticker) {
        return;
      }
      const last = this.points[this.points.length - 1];
      if (!last || payload.ts > last.ts) {
        this.points.push({ ts: payload.ts, price: payload.price });
        this.latestPrice = payload.price.toFixed(4);
        this.latestTime = new Date(payload.ts * 1000).toLocaleTimeString();
        this.updateChart();
      }
    });
    this.socket.on(
      'params_update',
      (payload: { ticker: string; volatility: number; drift: number }) => {
        if (!payload || payload.ticker !== this.ticker) {
          return;
        }
        this.volatility = payload.volatility.toString();
        this.drift = payload.drift.toString();
      }
    );
    this.socket.on('connect_error', () => {
      this.setStatus('Socket connection failed.', true);
    });
  }

  private async connectSocket(ticker: string): Promise<void> {
    this.setupSocket();
    if (!this.socket) {
      return;
    }
    if (this.socketTicker && this.socketTicker !== ticker) {
      this.socket.emit('unsubscribe', { ticker: this.socketTicker });
    }
    this.socketTicker = ticker;
    this.socket.emit('subscribe', { ticker });
  }

  private cleanupSocketSubscription(): void {
    if (!this.socket || !this.socketTicker) {
      return;
    }
    this.socket.emit('unsubscribe', { ticker: this.socketTicker });
    this.socketTicker = null;
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

  private async loadSimulationDt(): Promise<void> {
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
        if (!Number.isNaN(parsed.getTime())) {
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

  private isMarketOpen(date: Date): boolean {
    const start = new Date(date);
    start.setHours(9, 30, 0, 0);
    const end = new Date(date);
    end.setHours(16, 0, 0, 0);
    return date >= start && date <= end;
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
                return new Date(point.ts * 1000).toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                });
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
      new Date(p.ts * 1000).toLocaleTimeString()
    );
    this.chart.data.datasets[0].data = this.points.map((p) => p.price);
    this.chart.update();
  }
}
