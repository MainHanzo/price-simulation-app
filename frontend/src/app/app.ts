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
  points: PricePoint[] = [];
  showEmpty = true;

  private pollTimer: number | null = null;
  private chart: Chart | null = null;
  private clockTimer: number | null = null;
  private simulationBase: Date | null = null;
  private simulationStartMs: number | null = null;

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
    if (this.pollTimer) {
      window.clearInterval(this.pollTimer);
    }
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
    this.setStatus('Loading history...', false);

    if (this.pollTimer) {
      window.clearInterval(this.pollTimer);
    }

    try {
      const simulationNow = this.getSimulationDt();
      const inSession = this.isMarketOpen(simulationNow);
      await this.fetchHistory(raw);
      if (inSession) {
        await this.fetchLatest(raw);
        this.latestTime = simulationNow.toLocaleTimeString();
      }
      this.updateChart();
      if (inSession) {
        this.setStatus(`Streaming ${raw} every 60 seconds.`, false);
        this.pollTimer = window.setInterval(async () => {
          try {
            const now = this.getSimulationDt();
            if (!this.isMarketOpen(now)) {
              this.setStatus('Market closed — history only.', false);
              if (this.pollTimer) {
                window.clearInterval(this.pollTimer);
                this.pollTimer = null;
              }
              return;
            }
            await this.fetchLatest(raw);
            this.latestTime = now.toLocaleTimeString();
            this.updateChart();
          } catch {
            this.setStatus('Polling failed. Try searching again.', true);
          }
        }, 60000);
      } else {
        this.latestTime = simulationNow.toLocaleTimeString();
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

  private async fetchLatest(ticker: string): Promise<void> {
    const res = await fetch(`${this.apiBase}/api/latest/${ticker}`);
    if (!res.ok) {
      throw new Error('Ticker not found');
    }
    const data = (await res.json()) as PricePoint;
    const last = this.points[this.points.length - 1];
    if (!last || data.ts > last.ts) {
      this.points.push({ ts: data.ts, price: data.price });
    }
    this.latestPrice = data.price.toFixed(4);
  }

  private setLatestFromPoints(): void {
    const last = this.points[this.points.length - 1];
    if (!last) {
      this.latestPrice = '--';
      this.latestTime = '--';
      return;
    }
    this.latestPrice = last.price.toFixed(4);
  }

  private getSimulationDt(): Date {
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
      const now = this.getSimulationDt();
      this.currentFrontDisplay = now.toLocaleTimeString();
    };
    update();
    this.clockTimer = window.setInterval(update, 1000);
  }

  private async loadSimulationDt(): Promise<void> {
    try {
      const res = await fetch(`${this.apiBase}/api/config`);
      if (!res.ok) {
        return;
      }
      const data = (await res.json()) as { simulation_dt_iso?: string };
      if (data.simulation_dt_iso) {
        const parsed = new Date(data.simulation_dt_iso);
        if (!Number.isNaN(parsed.getTime())) {
          this.simulationDtIso = data.simulation_dt_iso;
          this.simulationBase = parsed;
          this.simulationStartMs = Date.now();
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
