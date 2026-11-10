import {
  AppRoot,
  Button,
  Cell,
  List,
  Navigation,
  Placeholder,
  Section,
  Spinner,
} from "@telegram-apps/telegram-ui";
import { useCallback, useEffect, useRef, useState } from "react";

import { get, type Me, type Result, type Status } from "./api";
import { BasketScreen } from "./BasketScreen";
import { ChinaScreen } from "./ChinaScreen";
import { MarketScreen } from "./MarketScreen";
import { PlanScreen } from "./PlanScreen";
import { TravelScreen } from "./TravelScreen";
import { platform, webApp } from "./telegram";

// Navigation: a Home list of full-width rows (Telegram's Settings pattern), not a bottom tab
// bar — five tabs left the outer icons in the phone's rounded corners (owner, 2026-11-10).
// Each row opens its screen; Telegram's back button returns Home.
const DEFAULT_SECTIONS = ["Today", "China", "Market", "Basket", "Travel"];
const ICONS: Record<string, string> = {
  Today: "📅",
  China: "🏮", // not the 🇨🇳 flag: Windows has no flag emoji and shows "CN"
  Market: "🌍",
  Basket: "🧺",
  Travel: "✈️",
};
const ABOUT: Record<string, string> = {
  Today: "Today, meals, training, the week",
  China: "Search, and your latest results",
  Market: "Watch list, prices to Yerevan",
  Basket: "Shopping list priced at two shops",
  Travel: "Cheapest trips, stays, searches",
};
// Every section has a real screen now (steps 1 and 2); an unknown name still shows "Coming soon".
const SCREENS: Record<string, (p: { onFail: (r: Result<unknown>) => void }) => JSX.Element> = {
  Today: PlanScreen,
  China: ChinaScreen,
  Market: MarketScreen,
  Basket: BasketScreen,
  Travel: TravelScreen,
};
const STATUS_EVERY_MS = 30_000;

// ?screen=china (the 📱 button under /china answers) opens that section directly.
function startSection(sections: string[]): string | null {
  const want = new URLSearchParams(window.location.search).get("screen")?.toLowerCase();
  return sections.find((s) => s.toLowerCase() === want) ?? null;
}

type Screen =
  | { kind: "loading" }
  | { kind: "private" }
  | { kind: "expired" }
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
  const [open, setOpen] = useState<string | null>(null); // null = Home

  useEffect(() => {
    const tg = webApp();
    tg?.ready();
    tg?.expand();
  }, []);

  const fail = useCallback((r: Result<unknown>) => {
    if (r.kind === "private" || r.kind === "expired" || r.kind === "unreachable" || r.kind === "slow") {
      setScreen({ kind: r.kind });
    }
  }, []);

  const refreshStatus = useCallback(async () => {
    const r = await get<Status>("/api/status");
    if (r.kind === "ok") {
      setStatus(r.data);
      setCheckedAt(
        new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }),
      );
    } else {
      fail(r);
    }
  }, [fail]);

  const load = useCallback(async () => {
    setScreen({ kind: "loading" });
    const r = await get<Me>("/api/me");
    if (r.kind !== "ok") return fail(r);
    setScreen({ kind: "ready", me: r.data });
    setOpen((cur) => cur ?? startSection(r.data.tabs.length ? r.data.tabs : DEFAULT_SECTIONS));
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

  // Telegram's back button: shown inside a section, returns Home
  const goHome = useCallback(() => setOpen(null), []);
  const backRef = useRef(goHome);
  backRef.current = goHome;
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
    if (open && screen.kind === "ready") bb.show();
    else bb.hide();
  }, [open, screen.kind]);

  const openSection = (name: string) => {
    webApp()?.HapticFeedback?.selectionChanged();
    setOpen(name);
    window.scrollTo(0, 0);
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
      {screen.kind === "expired" && (
        <div className="center">
          <Placeholder
            header="Session expired"
            description="This window has been open for more than a day. Close it and open the app again from 🏠 Family."
            action={
              <Button size="m" onClick={() => webApp()?.close()}>
                Close
              </Button>
            }
          >
            <span className="big">⌛</span>
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
      {screen.kind === "ready" &&
        (open ? (
          SCREENS[open] ? (
            (() => {
              const Screen = SCREENS[open];
              return <Screen onFail={fail} />;
            })()
          ) : (
            <SectionScreen name={open} onHome={goHome} />
          )
        ) : (
          <Home
            me={screen.me}
            status={status}
            checkedAt={checkedAt}
            onOpen={openSection}
            onRefresh={() => void refreshStatus()}
          />
        ))}
    </AppRoot>
  );
}

function Home(props: {
  me: Me;
  status: Status | null;
  checkedAt: string;
  onOpen: (name: string) => void;
  onRefresh: () => void;
}) {
  const { me, status, checkedAt, onOpen, onRefresh } = props;
  const sections = me.tabs.length ? me.tabs : DEFAULT_SECTIONS;
  return (
    <div className="page">
      <List>
        <Section>
          <Cell
            before={<span className="icon">🏠</span>}
            subtitle={`Signed in as ${me.name} · ${me.role}`}
          >
            Family
          </Cell>
        </Section>

        <Section>
          {sections.map((s) => (
            <Cell
              key={s}
              before={<span className="icon">{ICONS[s] ?? "•"}</span>}
              subtitle={ABOUT[s]}
              after={<Navigation />}
              onClick={() => onOpen(s)}
            >
              {s}
            </Cell>
          ))}
        </Section>

        <Section
          header="PC status"
          footer={status ? `Checked ${checkedAt} · version ${status.version}` : "Checking…"}
        >
          <Cell
            after={status ? status.time_local.slice(11) : "…"}
            subtitle={status?.time_local.slice(0, 10)}
          >
            Server time (Yerevan)
          </Cell>
          <Cell after={status?.ok ? "✅ reachable" : "…"} onClick={onRefresh}>
            PC
          </Cell>
        </Section>
      </List>
    </div>
  );
}

function SectionScreen(props: { name: string; onHome: () => void }) {
  const { name, onHome } = props;
  // Telegram's back button covers every current client; this row is the fallback for
  // a client too old to have one (Bot API < 6.1).
  const noBackButton = !webApp()?.isVersionAtLeast("6.1");
  return (
    <div className="page">
      <List>
        <Section header={name}>
          <Placeholder header="Coming soon" description={ABOUT[name] ?? `${name} will appear here.`}>
            <span className="big">{ICONS[name] ?? "✨"}</span>
          </Placeholder>
        </Section>
        {noBackButton && (
          <Section>
            <Cell before={<span className="icon">⬅️</span>} onClick={onHome}>
              Home
            </Cell>
          </Section>
        )}
      </List>
    </div>
  );
}
