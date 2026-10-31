import { Injectable, NgZone, OnDestroy } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { OrderBookSnapshot, OrderBookState } from './order-book.types';

@Injectable({ providedIn: 'root' })
export class OrderBookService implements OnDestroy {
  private readonly subject = new BehaviorSubject<OrderBookState>({ ticker: '', status: 'idle', snapshot: null });
  readonly state$ = this.subject.asObservable();
  private source: EventSource | null = null;
  private abort: AbortController | null = null;
  private generation = 0;
  private lastReceived = 0;
  private lastSequence: number | null = null;
  private staleTimer: number | null = null;

  constructor(private readonly zone: NgZone) {}

  async select(ticker: string): Promise<void> {
    this.disconnect();
    const generation = this.generation;
    this.subject.next({ ticker, status: 'loading', snapshot: null });
    const controller = new AbortController();
    this.abort = controller;
    try {
      const response = await fetch(`http://127.0.0.1:8000/api/orderbook/${encodeURIComponent(ticker)}`, { signal: controller.signal });
      if (!response.ok) throw new Error('Order book unavailable');
      const snapshot = await response.json() as OrderBookSnapshot;
      if (generation !== this.generation) return;
      this.accept(snapshot, ticker);
      this.staleTimer = window.setInterval(() => this.zone.run(() => this.checkStale()), 250);
      const source = new EventSource(`http://127.0.0.1:8000/api/orderbook/${encodeURIComponent(ticker)}/stream`);
      this.source = source;
      source.onopen = () => {
        if (generation === this.generation) this.lastSequence = null;
      };
      source.onmessage = (event) => this.zone.run(() => {
        if (generation !== this.generation) return;
        try { this.accept(JSON.parse(event.data) as OrderBookSnapshot, ticker); } catch { /* Wait for the next full snapshot. */ }
      });
      source.onerror = () => this.zone.run(() => {
        if (generation !== this.generation) return;
        this.checkStale();
        const state = this.subject.value;
        if (state.status !== 'stale') this.subject.next({ ...state, status: 'reconnecting' });
      });
    } catch {
      if (generation === this.generation) this.subject.next({ ticker, status: 'unavailable', snapshot: null });
    }
  }

  private accept(snapshot: OrderBookSnapshot, ticker: string): void {
    if (snapshot.ticker !== ticker || !Array.isArray(snapshot.bids) || !Array.isArray(snapshot.asks)) return;
    if (this.lastSequence !== null && snapshot.sequence < this.lastSequence) return;
    this.lastSequence = snapshot.sequence;
    this.lastReceived = Date.now();
    this.subject.next({ ticker, status: 'live', snapshot });
  }

  private checkStale(): void {
    const state = this.subject.value;
    if (state.snapshot?.session_status === 'open' && Date.now() - this.lastReceived >= 5000 && state.status !== 'stale') {
      this.subject.next({ ...state, status: 'stale' });
    }
  }

  disconnect(): void {
    this.generation++;
    this.lastSequence = null;
    this.abort?.abort();
    this.abort = null;
    this.source?.close();
    this.source = null;
    if (this.staleTimer !== null) window.clearInterval(this.staleTimer);
    this.staleTimer = null;
  }

  ngOnDestroy(): void { this.disconnect(); }
}
