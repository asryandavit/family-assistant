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

// private: the server refused who we are (401/403) — never says why.
// unreachable: no answer from the PC (off, tunnel down, timeout, gateway error).
export type Result<T> =
  | { kind: "ok"; data: T }
  | { kind: "private" }
  | { kind: "slow" }
  | { kind: "unreachable" };

const TIMEOUT_MS = 8000;

export async function get<T>(path: "/api/me" | "/api/status"): Promise<Result<T>> {
  const raw = initData();
  if (!raw) return { kind: "private" };
  const ctl = new AbortController();
  const timer = window.setTimeout(() => ctl.abort(), TIMEOUT_MS);
  try {
    const r = await fetch(path, {
      headers: { Authorization: `tma ${raw}` },
      cache: "no-store",
      credentials: "omit",
      signal: ctl.signal,
    });
    if (r.status === 401 || r.status === 403) return { kind: "private" };
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
