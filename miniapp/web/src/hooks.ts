import { useCallback, useEffect, useId, useRef, useState } from "react";

import { atLeast, webApp } from "./telegram";

// ---- MainButton: the screen's one main action in Telegram's bottom bar (6.0). Where the client
// has no MainButton the caller shows its own in-page button (`supported` is false).

export function useMainButton(o: {
  text: string;
  visible: boolean;
  active: boolean;
  loading: boolean;
  onClick: () => void;
}): boolean {
  const supported = !!webApp()?.MainButton && atLeast("6.0");
  const click = useRef(o.onClick);
  click.current = o.onClick;

  useEffect(() => {
    if (!supported) return;
    const mb = webApp()?.MainButton;
    if (!mb) return;
    const handler = () => click.current();
    mb.onClick(handler);
    return () => {
      mb.offClick(handler);
      try {
        mb.hideProgress();
        mb.hide();
      } catch {
        /* the screen is closing anyway */
      }
    };
  }, [supported]);

  useEffect(() => {
    if (!supported) return;
    const mb = webApp()?.MainButton;
    if (!mb) return;
    try {
      mb.setParams({ text: o.text, is_visible: o.visible, is_active: o.active && !o.loading });
      if (o.loading) mb.showProgress(false);
      else mb.hideProgress();
    } catch {
      /* a client that rejects the call keeps its last state */
    }
  }, [supported, o.text, o.visible, o.active, o.loading]);

  return supported;
}

// ---- closing confirmation (6.2) while any form holds text that was not sent

const dirtyForms = new Set<string>();

function applyClosingConfirmation() {
  const tg = webApp();
  if (!tg || !atLeast("6.2")) return;
  try {
    if (dirtyForms.size) tg.enableClosingConfirmation?.();
    else tg.disableClosingConfirmation?.();
  } catch {
    /* nicety */
  }
}

export function useClosingConfirmation(dirty: boolean) {
  const id = useId();
  useEffect(() => {
    if (dirty) dirtyForms.add(id);
    else dirtyForms.delete(id);
    applyClosingConfirmation();
    return () => {
      dirtyForms.delete(id);
      applyClosingConfirmation();
    };
  }, [dirty, id]);
}

// ---- small per-person UI preferences (never family data): Telegram CloudStorage (6.9) so they
// follow the person across devices, else this browser's localStorage. A stored value is only used
// if it is one of the allowed ones.

const PREF_WAIT_MS = 1500;

function readPref(key: string, cb: (v: string | null) => void) {
  const tg = webApp();
  if (tg?.CloudStorage && atLeast("6.9")) {
    try {
      tg.CloudStorage.getItem(key, (err, v) => cb(!err && typeof v === "string" && v ? v : null));
      return;
    } catch {
      /* fall through to localStorage */
    }
  }
  try {
    cb(window.localStorage.getItem(key));
  } catch {
    cb(null);
  }
}

function writePref(key: string, value: string) {
  const tg = webApp();
  if (tg?.CloudStorage && atLeast("6.9")) {
    try {
      tg.CloudStorage.setItem(key, value);
      return;
    } catch {
      /* fall through */
    }
  }
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* private mode: the choice just isn't remembered */
  }
}

/** [value, set, ready]. `ready` turns true once the stored value is read (or after 1.5 s). */
export function usePref<T extends string>(key: string, allowed: readonly T[], fallback: T) {
  const [value, setValue] = useState<T>(fallback);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let done = false;
    const finish = (v: string | null) => {
      if (done) return;
      done = true;
      if (v && (allowed as readonly string[]).includes(v)) setValue(v as T);
      setReady(true);
    };
    const timer = window.setTimeout(() => finish(null), PREF_WAIT_MS);
    readPref(`ui_${key}`, (v) => {
      window.clearTimeout(timer);
      finish(v);
    });
    return () => {
      done = true;
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  const set = useCallback(
    (v: T) => {
      setValue(v);
      writePref(`ui_${key}`, v);
    },
    [key],
  );
  return [value, set, ready] as const;
}

// ---- "Add to home screen" (8.0). status: unsupported | unknown | added | missed

export function useHomeScreen() {
  const [status, setStatus] = useState("");
  useEffect(() => {
    const tg = webApp();
    if (!tg?.checkHomeScreenStatus || !atLeast("8.0")) return;
    try {
      tg.checkHomeScreenStatus((s) => setStatus(String(s)));
    } catch {
      /* unsupported */
    }
  }, []);
  const add = useCallback(() => {
    try {
      webApp()?.addToHomeScreen?.();
    } catch {
      /* unsupported */
    }
  }, []);
  // "unknown" = it can be added but the client cannot tell whether it already was
  return { available: status === "missed" || status === "unknown", add };
}
