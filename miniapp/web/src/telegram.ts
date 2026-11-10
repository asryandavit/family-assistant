// The small part of Telegram.WebApp (telegram-web-app.js) this app uses.
// Reference: https://core.telegram.org/bots/webapps
export interface TelegramWebApp {
  initData: string; // raw signed string; the only thing sent to the server
  colorScheme: "light" | "dark";
  platform: string;
  version: string;
  ready(): void;
  expand(): void;
  isVersionAtLeast(v: string): boolean;
  setHeaderColor?(color: string): void;
  setBackgroundColor?(color: string): void;
  onEvent(event: "themeChanged", cb: () => void): void;
  offEvent(event: "themeChanged", cb: () => void): void;
  BackButton: {
    isVisible: boolean;
    show(): void;
    hide(): void;
    onClick(cb: () => void): void;
    offClick(cb: () => void): void;
  };
  HapticFeedback?: {
    selectionChanged(): void;
    notificationOccurred(type: "error" | "success" | "warning"): void;
  };
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
