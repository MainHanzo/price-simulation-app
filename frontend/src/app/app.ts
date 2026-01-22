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
  private ctx: CanvasRenderingContext2D | null = null;

  @ViewChild('priceChart', { static: true })
  canvasRef!: ElementRef<HTMLCanvasElement>;

  @HostListener('window:resize')
  onResize() {
    this.resizeCanvas();
    this.drawChart();
  }

  ngAfterViewInit(): void {
    this.resizeCanvas();
    this.drawChart();
  }

  ngOnDestroy(): void {
    if (this.pollTimer) {
      window.clearInterval(this.pollTimer);
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
      this.drawChart();
      this.setStatus(`Streaming ${raw} every 60 seconds.`, false);
      this.pollTimer = window.setInterval(async () => {
        try {
          await this.fetchLatest(raw);
          this.drawChart();
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

  private resizeCanvas(): void {
    const canvas = this.canvasRef.nativeElement;
    const ratio = window.devicePixelRatio || 1;
    canvas.width = canvas.clientWidth * ratio;
    canvas.height = canvas.clientHeight * ratio;
    this.ctx = canvas.getContext('2d');
    if (this.ctx) {
      this.ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    }
  }

  private drawChart(): void {
    const canvas = this.canvasRef.nativeElement;
    const ctx = this.ctx;
    if (!ctx) {
      return;
    }

    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    ctx.clearRect(0, 0, width, height);

    if (!this.points.length) {
      this.showEmpty = true;
      return;
    }
    this.showEmpty = false;

    const padding = 36;
    const prices = this.points.map((p) => p.price);
    let minPrice = Math.min(...prices);
    let maxPrice = Math.max(...prices);
    if (minPrice === maxPrice) {
      minPrice -= 1;
      maxPrice += 1;
    }

    const minTs = this.points[0].ts;
    const maxTs = this.points[this.points.length - 1].ts || minTs + 1;
    const span = maxTs - minTs || 1;

    ctx.lineWidth = 2;
    ctx.strokeStyle = '#d97706';
    ctx.beginPath();

    this.points.forEach((point, idx) => {
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

    ctx.strokeStyle = 'rgba(31, 26, 23, 0.2)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padding, padding);
    ctx.lineTo(padding, height - padding);
    ctx.lineTo(width - padding, height - padding);
    ctx.stroke();

    ctx.fillStyle = '#5b4b43';
    ctx.font = "12px 'Space Grotesk', sans-serif";
    ctx.fillText(maxPrice.toFixed(2), padding + 6, padding + 12);
    ctx.fillText(minPrice.toFixed(2), padding + 6, height - padding + 18);
  }
}
