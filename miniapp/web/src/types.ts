// Display JSON for the step 2 screens (miniapp/screens.py, miniapp/actions.py). Every number
// and sentence is already finished on the PC; the page only lays it out.

export interface Seg {
  t: string;
  b?: 1;
  i?: 1;
  c?: 1;
  a?: string;
}
export type Block =
  | { k: "p"; s: Seg[] }
  | { k: "fold"; title: string; b: { k: "p"; s: Seg[] }[] };

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
  unavailable: boolean;
  trips: {
    route: string;
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
    why: string;
    url: string | null;
  }[];
  stays_date?: string;
}

export interface ChinaStatus {
  running: boolean;
  waiting: number;
}

export interface Reply {
  ok: boolean;
  message: string;
}
