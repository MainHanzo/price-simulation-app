import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';
import { OrderBookLevel, OrderBookState } from './order-book.types';

@Component({
  selector: 'app-order-book',
  imports: [CommonModule],
  templateUrl: './order-book.html',
  styleUrl: './order-book.css',
})
export class OrderBook {
  @Input({ required: true }) state!: OrderBookState;

  get asks(): OrderBookLevel[] { return [...(this.state.snapshot?.asks ?? [])].reverse(); }
  get spread(): number {
    const book = this.state.snapshot;
    return book?.asks.length && book?.bids.length ? book.asks[0].price - book.bids[0].price : 0;
  }
  get statusLabel(): string {
    if (this.state.snapshot?.session_status === 'closed') return 'Market closed';
    return { idle: 'Awaiting a symbol', loading: 'Loading', live: 'Live · 1 second', reconnecting: 'Reconnecting', stale: 'Stale · reconnecting', unavailable: 'Unavailable' }[this.state.status];
  }
  depth(level: OrderBookLevel, side: 'asks' | 'bids'): number {
    const levels = this.state.snapshot?.[side] ?? [];
    const total = levels[levels.length - 1]?.cumulative_quantity ?? 1;
    return 100 * level.cumulative_quantity / total;
  }
  time(epoch: number): string {
    return new Date(epoch * 1000).toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }
}
