import { initData } from "./telegram";

export interface Me {
  name: string;
  role: string;
  tabs: string[];
}

export interface Status {
  ok: boolean;
  time_local: string;
  tz: string;
  version: string;
}

// GET /api/china — display JSON built on the PC (miniapp/china_view.py). Every number is
// already a finished string; the page only shows them.
export interface ChinaCard {
  n: number;
  pick: boolean;
  site: string;
  site_name: string;
  title: string;
  title_cn: string;
  variant: string | null;
  seller: string;
  trust: number | null;
  trust_line: string | null;
  price: string;
  notes: string[];
  total: string | null;
  routes: string[];
  weight: string[];
  delivery: string | null;
  sales: string | null;
  min_order: string | null;
  specs: string[];
  material: string | null;
  size: string | null;
  reviews: { read: boolean; count: string | null; liked: string[]; complaints: string[] };
  flags: string[];
  why: string | null;
  ask_seller: string | null;
  link: string | null;
  can_watch: boolean;
  can_reviews: boolean;
}

export type China =
  | { empty: true }
  | {
      empty: false;
      job: string;
      kind: string;
      query: string;
      query_cn: string | null;
      sent: string;
      sites: { site: string; name: string; status: string; line: string }[];
      pick: number | null;
      pick_reason: string | null;
      results: ChinaCard[];
    };

export interface ActionReply {
  ok: boolean;
  message: string;
}

// private: the server refused who we are (401/403) — never says why.
// expired: Telegram's signature was valid but the session is older than the server accepts;
//          closing and reopening the app gets a fresh one.
// unreachable: no answer from the PC (off, tunnel down, timeout, gateway error).
export type Result<T> =
  | { kind: "ok"; data: T }
  | { kind: "private" }
  | { kind: "expired" }
  | { kind: "slow" }
  | { kind: "unreachable" };

const TIMEOUT_MS = 8000;
// an action may wait for the watch-list lock (30 s) and the Google Sheet
const ACTION_TIMEOUT_MS = 45000;

export function get<T>(path: "/api/me" | "/api/status" | "/api/china"): Promise<Result<T>> {
  return call<T>(path);
}

export function post<T>(path: "/api/china/action", body: object): Promise<Result<T>> {
  return call<T>(path, body);
}

async function call<T>(path: string, body?: object): Promise<Result<T>> {
  const raw = initData();
  if (!raw) return { kind: "private" };
  const ctl = new AbortController();
  const timer = window.setTimeout(() => ctl.abort(), body ? ACTION_TIMEOUT_MS : TIMEOUT_MS);
  try {
    const headers: Record<string, string> = { Authorization: `tma ${raw}` };
    if (body) headers["Content-Type"] = "application/json";
    const r = await fetch(path, {
      method: body ? "POST" : "GET",
      headers,
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
      credentials: "omit",
      signal: ctl.signal,
    });
    if (r.status === 401) {
      const why = (await r.json().catch(() => null)) as { error?: string } | null;
      return why?.error === "expired" ? { kind: "expired" } : { kind: "private" };
    }
    if (r.status === 403) return { kind: "private" };
    if (r.status === 429) return { kind: "slow" };
    const type = r.headers.get("Content-Type") ?? "";
    if (!r.ok || !type.startsWith("application/json")) return { kind: "unreachable" };
    return { kind: "ok", data: (await r.json()) as T };
  } catch {
    return { kind: "unreachable" };
  } finally {
    window.clearTimeout(timer);
  }
}
