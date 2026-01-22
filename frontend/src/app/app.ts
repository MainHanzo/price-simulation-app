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
  latestPrice = '--';
  statusMsg = '';
  isError = false;
  points: PricePoint[] = [];
  showEmpty = true;

  private pollTimer: number | null = null;
  private chart: Chart | null = null;

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
  }

  ngOnDestroy(): void {
    if (this.pollTimer) {
      window.clearInterval(this.pollTimer);
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
      await this.fetchHistory(raw);
      await this.fetchLatest(raw);
      this.updateChart();
      this.setStatus(`Streaming ${raw} every 60 seconds.`, false);
      this.pollTimer = window.setInterval(async () => {
        try {
          await this.fetchLatest(raw);
          this.updateChart();
        } catch {
          this.setStatus('Polling failed. Try searching again.', true);
        }
      }, 60000);
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
