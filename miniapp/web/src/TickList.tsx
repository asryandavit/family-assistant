import { Button, Cell, Placeholder, Section, Spinner } from "@telegram-apps/telegram-ui";
import { type MouseEvent, useCallback, useEffect, useRef, useState } from "react";

import { get, post, type Result } from "./api";
import { Notice, openLink, type Msg } from "./common";
import { confirmAsk, haptic } from "./telegram";
import type { Reply, ShopItem, ShopList } from "./types";

// The shared shopping list (decision 108): the same state as /list in the chat. Tap a row to
// tick it for the whole household; ⓘ shows where it comes from and why that pick. The other
// person's ticks arrive by a quiet refresh every 15 s while the screen is open.

type Data = ShopList | { unavailable: true; message: string };
type Answer = Reply & { view: ShopList | null };

const POLL_MS = 15_000;

function lastTick(list: ShopList): string | undefined {
  return list.last ? `Last ticked: ${list.last.item} · ${list.last.by_name} ${list.last.at}` : undefined;
}

export function TickList(props: { kind: "weekly" | "monthly"; onFail: (r: Result<unknown>) => void }) {
  const { kind, onFail } = props;
  const [data, setData] = useState<Data | null>(null);
  const [failed, setFailed] = useState(false);
  const [msg, setMsg] = useState<Msg>(null);
  const [open, setOpen] = useState<string | null>(null);
  const inFlight = useRef(0);
  const failRef = useRef(onFail);
  failRef.current = onFail;

  const load = useCallback(async () => {
    const r = await get<Data>(`/api/list/${kind}`);
    if (r.kind === "ok") {
      if (inFlight.current === 0) setData(r.data); // never overwrite a tick that is still on its way
      setFailed(false);
    } else if (r.kind === "private" || r.kind === "expired") failRef.current(r);
    else setFailed(true);
  }, [kind]);

  useEffect(() => {
    setData(null);
    setOpen(null);
    setMsg(null);
    void load();
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [kind, load]);

  const apply = (answer: Answer) => {
    if (answer.view) setData(answer.view);
    setMsg(answer.ok ? null : { ok: false, text: answer.message });
  };

  const tick = async (item: ShopItem) => {
    const list = data;
    if (!list || "unavailable" in list) return;
    haptic("tap");
    // show the tick at once; the server's answer replaces it (or it is undone and says why)
    setData({
      ...list,
      done: list.done + (item.done ? -1 : 1),
      groups: list.groups.map((g) => ({
        ...g,
        items: g.items.map((i) =>
          i.key === item.key ? { ...i, done: !i.done, by_name: i.done ? null : "you", at: i.done ? null : "now" } : i,
        ),
      })),
    });
    inFlight.current += 1;
    const r = await post<Answer>("/api/list/tick", { kind, key: item.key, done: item.done ? "0" : "1" });
    inFlight.current -= 1;
    if (r.kind === "ok") {
      apply(r.data);
      if (!r.data.ok) {
        haptic("warn");
        void load(); // the list changed under us: show what it is now
      }
    } else {
      setMsg({ ok: false, text: r.kind === "slow" ? "Too many requests — wait a minute." : "The PC did not answer — the tick was not saved." });
      haptic("error");
      void load();
    }
  };

  const reset = async () => {
    if (!data || "unavailable" in data) return;
    const what = kind === "weekly" ? "week" : "month";
    const ticks = data.done === 1 ? "the 1 tick" : `all ${data.done} ticks`;
    if (!(await confirmAsk(`Clear ${ticks} and start a new ${what}? The items stay.`))) return;
    const r = await post<Answer>("/api/list/reset", { kind });
    if (r.kind === "ok") apply(r.data);
    else setMsg({ ok: false, text: "The PC did not answer — nothing was cleared." });
  };

  if (failed && !data) {
    return (
      <Section header="Tick list">
        <Placeholder
          header="Could not load the list"
          description="The PC did not answer."
          action={
            <Button size="m" onClick={() => void load()}>
              Try again
            </Button>
          }
        >
          <span className="big">✅</span>
        </Placeholder>
      </Section>
    );
  }
  if (!data) {
    return (
      <div className="center short">
        <Spinner size="l" />
      </div>
    );
  }
  if ("unavailable" in data) {
    return (
      <Section header="Tick list">
        <Placeholder header="The list could not be read" description={data.message}>
          <span className="big">✅</span>
        </Placeholder>
      </Section>
    );
  }

  return (
    <>
      <Section header={`Tick list · ${data.period_label}`} footer={lastTick(data)}>
        {data.total > 0 && (
          <div className="progress-row">
            <div
              className="progress"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={data.total}
              aria-valuenow={data.done}
              aria-label="Items in the cart"
            >
              <div className="progress-fill" style={{ width: `${(100 * data.done) / data.total}%` }} />
            </div>
            <span className="progress-text">
              {data.done === data.total ? `All ${data.total} in the cart 🎉` : `${data.done} of ${data.total} in the cart`}
            </span>
          </div>
        )}
        {data.total === 0 && (
          <Placeholder header="Nothing on this list" description="basket.md has no rows for it.">
            <span className="big">✅</span>
          </Placeholder>
        )}
        <Notice msg={msg} />
      </Section>
      {data.groups.map((g) => (
        <Section key={g.aisle} header={g.aisle}>
          {g.items.map((i) => (
            <Row key={i.key} item={i} open={open === i.key} onTick={() => void tick(i)} onInfo={() => setOpen(open === i.key ? null : i.key)} />
          ))}
        </Section>
      ))}
      {data.total > 0 && (
        <Section footer={data.reset ? `Cleared by ${data.reset.by_name} ${data.reset.at}` : undefined}>
          <div className="actions">
            <Button size="s" mode="bezeled" disabled={data.done === 0} onClick={() => void reset()}>
              ♻️ New {kind === "weekly" ? "week" : "month"} — clear the ticks
            </Button>
          </div>
        </Section>
      )}
    </>
  );
}

function Row(props: { item: ShopItem; open: boolean; onTick: () => void; onInfo: () => void }) {
  const { item: i, open, onTick, onInfo } = props;
  const where = [i.amount, i.shop_name].filter(Boolean).join(" · ");
  const who = i.done && i.by_name ? ` · ✓ ${i.by_name}${i.at ? ` ${i.at}` : ""}` : "";
  const hasInfo = !!(i.reason || i.product || i.url);
  return (
    <>
      <Cell
        multiline
        before={<span className={i.done ? "box on" : "box"} aria-hidden="true">{i.done ? "✓" : ""}</span>}
        subtitle={`${where}${who}` || undefined}
        after={
          hasInfo || i.cost ? (
            <span className="row-after">
              {i.cost && <span className="hint nowrap">{i.cost}</span>}
              {hasInfo && (
                <button
                  type="button"
                  className="info"
                  aria-label={`Why this pick: ${i.item}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    onInfo();
                  }}
                >
                  ⓘ
                </button>
              )}
            </span>
          ) : undefined
        }
        onClick={(e: MouseEvent) => {
          // the ⓘ button sits inside the row; a tap on it (or on the row's ripple layer over
          // it) must open the details, never tick (seen in Telegram Web, 2026-11-16)
          if ((e.target as HTMLElement).closest?.(".info")) return;
          onTick();
        }}
      >
        <span className={i.done ? "struck" : undefined}>{i.item}</span>
      </Cell>
      {open && (
        <div className="details">
          {i.buy && <div className="lines">Buy: {i.buy}{i.shop_name ? ` at ${i.shop_name}` : ""}</div>}
          {i.product && <div className="lines">Product: {i.product}</div>}
          {i.reason ? <div className="why">{i.reason}</div> : <div className="lines">No special reason: the best-value acceptable product.</div>}
          {i.url && (
            <div className="actions">
              <Button size="s" mode="bezeled" onClick={() => openLink(i.url as string)}>
                Open the product
              </Button>
            </div>
          )}
        </div>
      )}
    </>
  );
}
