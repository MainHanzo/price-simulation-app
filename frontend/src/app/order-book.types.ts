export interface OrderBookLevel {
  price: number;
  quantity: number;
  cumulative_quantity: number;
}

export interface OrderBookSnapshot {
  ticker: string;
  sequence: number;
  ts: number;
  reference_price: number;
  reference_ts: number;
  session_status: 'open' | 'closed';
  bids: OrderBookLevel[];
  asks: OrderBookLevel[];
}

export type BookStatus = 'idle' | 'loading' | 'live' | 'reconnecting' | 'stale' | 'unavailable';
export interface OrderBookState {
  ticker: string;
  status: BookStatus;
  snapshot: OrderBookSnapshot | null;
}
