// The part of Telegram.WebApp (telegram-web-app.js) this app uses.
// Reference: https://core.telegram.org/bots/webapps — each feature below names the version the
// docs give for it (read 2026-11-15). The script exposes every method whatever the user's
// Telegram client can do, so every use goes through `atLeast()` and a try/catch.
export interface BottomButton {
  isVisible: boolean;
  isActive: boolean;
  isProgressVisible: boolean;
  setParams(p: { text?: string; is_visible?: boolean; is_active?: boolean }): BottomButton;
  show(): BottomButton;
  hide(): BottomButton;
  showProgress(leaveActive?: boolean): BottomButton;
  hideProgress(): BottomButton;
  onClick(cb: () => void): BottomButton;
  offClick(cb: () => void): BottomButton;
}

type CloudCb<T> = (error: string | null, value?: T) => void;

export interface TelegramWebApp {
  initData: string; // raw signed string; the only thing sent to the server
  colorScheme: "light" | "dark";
  platform: string;
  version: string;
  ready(): void;
  expand(): void;
  close(): void;
  isVersionAtLeast(v: string): boolean;
  setHeaderColor?(color: string): void; // 6.1; "secondary_bg_color" keyword
  setBackgroundColor?(color: string): void; // 6.1
  onEvent(event: "themeChanged", cb: () => void): void;
  offEvent(event: "themeChanged", cb: () => void): void;
  BackButton: {
    isVisible: boolean;
    show(): void;
    hide(): void;
    onClick(cb: () => void): void;
    offClick(cb: () => void): void;
  };
  MainButton?: BottomButton; // 6.0 (renamed BottomButton in 7.10)
  HapticFeedback?: {
    selectionChanged(): void;
    impactOccurred(style: "light" | "medium" | "heavy" | "rigid" | "soft"): void;
    notificationOccurred(type: "error" | "success" | "warning"): void;
  };
  // 6.9: keys 1–128 chars [A-Za-z0-9_-], values 0–4096 chars, 1024 items per bot per user.
  CloudStorage?: {
    setItem(key: string, value: string, cb?: CloudCb<boolean>): void;
    getItem(key: string, cb: CloudCb<string>): void;
  };
  showConfirm?(message: string, cb?: (ok: boolean) => void): void; // 6.2
  enableClosingConfirmation?(): void; // 6.2
  disableClosingConfirmation?(): void;
  // 8.0: "unsupported" | "unknown" | "added" | "missed"
  addToHomeScreen?(): void;
  checkHomeScreenStatus?(cb?: (status: string) => void): void;
  // Opens a link outside the app (the phone's browser, or the store's app for its links).
  openLink(url: string): void;
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}

export function webApp(): TelegramWebApp | undefined {
  return window.Telegram?.WebApp;
}

export function initData(): string {
  return webApp()?.initData ?? "";
}

export function platform(): "ios" | "base" {
  const p = webApp()?.platform ?? "";
  return p === "ios" || p === "macos" ? "ios" : "base";
}

/** True if this Telegram client reports at least Bot API version `v` (never throws). */
export function atLeast(v: string): boolean {
  try {
    return !!webApp()?.isVersionAtLeast(v);
  } catch {
    return false;
  }
}

export type Haptic = "select" | "tap" | "ok" | "warn" | "error";

/** Haptic feedback where the client has it (6.1); silently nothing elsewhere. */
export function haptic(kind: Haptic): void {
  try {
    const h = webApp()?.HapticFeedback;
    if (!h || !atLeast("6.1")) return;
    if (kind === "select") h.selectionChanged();
    else if (kind === "tap") h.impactOccurred("light");
    else h.notificationOccurred(kind === "ok" ? "success" : kind === "warn" ? "warning" : "error");
  } catch {
    /* feedback is a nicety */
  }
}

/** A native confirm popup (6.2), falling back to the browser's. */
export function confirmAsk(message: string): Promise<boolean> {
  const tg = webApp();
  if (tg?.showConfirm && atLeast("6.2")) {
    return new Promise((resolve) => {
      try {
        tg.showConfirm?.(message, (ok) => resolve(!!ok));
      } catch {
        resolve(window.confirm(message));
      }
    });
  }
  return Promise.resolve(window.confirm(message));
}
