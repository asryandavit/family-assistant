// Display JSON for the step 2 screens (miniapp/screens.py, miniapp/actions.py). Every number
// and sentence is already finished on the PC; the page only lays it out.

export interface Seg {
  t: string;
  b?: 1;
  i?: 1;
  c?: 1;
  a?: string;
}
export type Para = { k: "p"; s: Seg[] };
export type Gap = { k: "gap" };
// a "gap" is an empty line in the chat's text: the page starts a new card there
export type Block = Para | Gap | { k: "fold"; title: string; b: (Para | Gap)[] };

export type Page = { unreadable: true } | { unreadable?: false; title: string; blocks: Block[] };

export interface MarketItem {
  n: number;
  id: string;
  name: string;
  stores: string[];
  qty: number;
  added_by: string;
  best: string | null;
  weight_needed: boolean;
  links: string[];
}
export interface Market {
  items: MarketItem[];
  stores: string[];
  note: string;
}

export interface BasketItem {
  item: string;
  buy: string;
  product: string;
  cost: string;
  url: string | null;
}
export type Basket =
  | { empty: true; kind: string }
  | {
      empty: false;
      kind: string;
      when: string;
      // "28 days old — Price the list now for fresh prices", built on the PC; null when fresh
      stale: string | null;
      total: string;
      partial: boolean;
      compare: string | null;
      groups: { shop: string; name: string; dot: string; subtotal: string | null; items: BasketItem[] }[];
      unpriced: string[];
      skipped: string[];
    };

export interface Travel {
  scan: { enabled: boolean; next: string | null; last: string | null } | null;
  run_date: string | null;
  run_label?: string;
  unavailable: boolean;
  trips: {
    route: string;
    name?: string;
    codes?: string;
    kind: string;
    out: string;
    back: string;
    nights: string;
    pax: string;
    currency: string;
    total: string;
    club: string | null;
  }[];
  stays: {
    city: string;
    in: string;
    out: string;
    nights: string;
    source: string;
    name: string;
    rating: string;
    currency: string;
    total: string;
    night: string;
    why: string | null;
    url: string | null;
  }[];
  stays_date?: string;
  stays_label?: string;
  // "5 days old — Scan now for fresh prices", built on the PC; null when fresh
  trips_note: string | null;
  stays_note: string | null;
}

export interface ChinaStatus {
  running: boolean;
  waiting: number;
}

// The shared tick list (miniapp/shopping_view.py): names, not ids; Yerevan time
export interface ShopItem {
  key: string;
  item: string;
  amount: string;
  shop_name: string | null;
  buy: string | null;
  product: string | null;
  url: string | null;
  reason: string | null;
  cost: string | null;
  done: boolean;
  by_name: string | null;
  at: string | null;
}
export interface ShopList {
  kind: string;
  period_label: string;
  version: string;
  done: number;
  total: number;
  groups: { aisle: string; items: ShopItem[] }[];
  last: { item: string; by_name: string; at: string } | null;
  reset: { by_name: string; at: string } | null;
}

export interface Reply {
  ok: boolean;
  message: string;
}
