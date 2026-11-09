import {
  AppRoot,
  Button,
  Cell,
  List,
  Placeholder,
  Section,
  Spinner,
  Tabbar,
} from "@telegram-apps/telegram-ui";
import { useCallback, useEffect, useRef, useState } from "react";

import { get, type Me, type Result, type Status } from "./api";
import { platform, webApp } from "./telegram";

const DEFAULT_TABS = ["Today", "China", "Market", "Basket", "Travel"];
const ICONS: Record<string, string> = {
  Today: "📅",
  China: "🇨🇳",
  Market: "🌍",
  Basket: "🧺",
  Travel: "✈️",
};
const STATUS_EVERY_MS = 30_000;

type Screen =
  | { kind: "loading" }
  | { kind: "private" }
  | { kind: "unreachable" }
  | { kind: "slow" }
  | { kind: "ready"; me: Me };

function useAppearance(): "light" | "dark" {
  const [scheme, setScheme] = useState<"light" | "dark">(webApp()?.colorScheme ?? "light");
  useEffect(() => {
    const tg = webApp();
    if (!tg) return;
    const onTheme = () => setScheme(tg.colorScheme);
    tg.onEvent("themeChanged", onTheme);
    return () => tg.offEvent("themeChanged", onTheme);
  }, []);
  return scheme;
}

export function App() {
  const appearance = useAppearance();
  const [screen, setScreen] = useState<Screen>({ kind: "loading" });
  const [status, setStatus] = useState<Status | null>(null);
  const [checkedAt, setCheckedAt] = useState<string>("");
  const [history, setHistory] = useState<string[]>([DEFAULT_TABS[0]]);
  const tab = history[history.length - 1];

  useEffect(() => {
    const tg = webApp();
    tg?.ready();
    tg?.expand();
  }, []);

  const fail = useCallback((r: Result<unknown>) => {
    if (r.kind === "private" || r.kind === "unreachable" || r.kind === "slow") {
      setScreen({ kind: r.kind });
    }
  }, []);

  const refreshStatus = useCallback(async () => {
    const r = await get<Status>("/api/status");
    if (r.kind === "ok") {
      setStatus(r.data);
      setCheckedAt(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }));
    } else {
      fail(r);
    }
  }, [fail]);

  const load = useCallback(async () => {
    setScreen({ kind: "loading" });
    const r = await get<Me>("/api/me");
    if (r.kind !== "ok") return fail(r);
    setScreen({ kind: "ready", me: r.data });
    void refreshStatus();
  }, [fail, refreshStatus]);

  useEffect(() => {
    void load();
  }, [load]);

  // keep the status card honest while the app is open; a stopped PC shows up on its own
  useEffect(() => {
    if (screen.kind !== "ready") return;
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") void refreshStatus();
    }, STATUS_EVERY_MS);
    return () => window.clearInterval(id);
  }, [screen.kind, refreshStatus]);

  // Telegram's back button walks back through the tabs visited
  const goBack = useCallback(() => setHistory((h) => (h.length > 1 ? h.slice(0, -1) : h)), []);
  const backRef = useRef(goBack);
  backRef.current = goBack;
  useEffect(() => {
    const bb = webApp()?.BackButton;
    if (!bb) return;
    const onClick = () => backRef.current();
    bb.onClick(onClick);
    return () => bb.offClick(onClick);
  }, []);
  useEffect(() => {
    const bb = webApp()?.BackButton;
    if (!bb) return;
    if (history.length > 1 && screen.kind === "ready") bb.show();
    else bb.hide();
  }, [history.length, screen.kind]);

  const openTab = (name: string) => {
    if (name === tab) return;
    webApp()?.HapticFeedback?.selectionChanged();
    setHistory((h) => [...h.filter((t) => t !== name), name]);
    void refreshStatus();
  };

  return (
    <AppRoot appearance={appearance} platform={platform()}>
      {screen.kind === "loading" && (
        <div className="center">
          <Spinner size="l" />
        </div>
      )}
      {screen.kind === "private" && (
        <div className="center">
          <Placeholder
            header="This app is private"
            description="It opens only for the family, from the 🏠 Family button in the bot's chat."
          >
            <span className="big">🔒</span>
          </Placeholder>
        </div>
      )}
      {screen.kind === "unreachable" && (
        <div className="center">
          <Placeholder
            header="PC is not reachable"
            description="The family PC is off, asleep or offline. Try again when it is on."
            action={
              <Button size="m" onClick={() => void load()}>
                Try again
              </Button>
            }
          >
            <span className="big">🖥️</span>
          </Placeholder>
        </div>
      )}
      {screen.kind === "slow" && (
        <div className="center">
          <Placeholder
            header="Too many requests"
            description="Wait a minute, then try again."
            action={
              <Button size="m" onClick={() => void load()}>
                Try again
              </Button>
            }
          >
            <span className="big">⏳</span>
          </Placeholder>
        </div>
      )}
      {screen.kind === "ready" && (
        <Ready
          me={screen.me}
          tab={tab}
          status={status}
          checkedAt={checkedAt}
          onTab={openTab}
          onRefresh={() => void refreshStatus()}
        />
      )}
    </AppRoot>
  );
}

function Ready(props: {
  me: Me;
  tab: string;
  status: Status | null;
  checkedAt: string;
  onTab: (t: string) => void;
  onRefresh: () => void;
}) {
  const { me, tab, status, checkedAt, onTab, onRefresh } = props;
  const tabs = me.tabs.length ? me.tabs : DEFAULT_TABS;
  return (
    <div className="page">
      <List>
        <Section>
          <Cell before={<span className="icon">🏠</span>} subtitle={`Signed in as ${me.name} · ${me.role}`}>
            Family
          </Cell>
        </Section>

        <Section header={tab}>
          <Placeholder header="Coming soon" description={`${tab} will appear here.`}>
            <span className="big">{ICONS[tab] ?? "✨"}</span>
          </Placeholder>
        </Section>

        <Section
          header="PC status"
          footer={status ? `Checked ${checkedAt} · version ${status.version}` : "Checking…"}
        >
          <Cell after={status ? status.time_local.slice(11) : "…"} subtitle={status?.time_local.slice(0, 10)}>
            Server time (Yerevan)
          </Cell>
          <Cell after={status?.ok ? "✅ reachable" : "…"} onClick={onRefresh}>
            PC
          </Cell>
        </Section>
      </List>

      <Tabbar>
        {tabs.map((t) => (
          <Tabbar.Item key={t} text={t} selected={t === tab} onClick={() => onTab(t)}>
            <span className="icon">{ICONS[t] ?? "•"}</span>
          </Tabbar.Item>
        ))}
      </Tabbar>
    </div>
  );
}
