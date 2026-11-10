import { Button, Cell, List, Placeholder, Section, Spinner } from "@telegram-apps/telegram-ui";
import { useCallback, useEffect, useState } from "react";

import { get, post, type ActionReply, type China, type ChinaCard, type Result } from "./api";
import { webApp } from "./telegram";

// Step 1 (docs/briefs/MINI_APP.md §12): the person's latest /china result. Every number is a
// finished string from the PC (miniapp/china_view.py); this file only lays it out.

type Load = { kind: "loading" } | { kind: "ok"; data: China } | { kind: "failed" };

export function ChinaScreen(props: { onFail: (r: Result<unknown>) => void }) {
  const { onFail } = props;
  const [load, setLoad] = useState<Load>({ kind: "loading" });

  const fetchIt = useCallback(async () => {
    const r = await get<China>("/api/china");
    if (r.kind === "ok") setLoad({ kind: "ok", data: r.data });
    else if (r.kind === "private" || r.kind === "expired") onFail(r);
    else setLoad({ kind: "failed" });
  }, [onFail]);

  useEffect(() => {
    void fetchIt();
  }, [fetchIt]);

  if (load.kind === "loading") {
    return (
      <div className="center">
        <Spinner size="l" />
      </div>
    );
  }
  if (load.kind === "failed") {
    return (
      <div className="center">
        <Placeholder
          header="Could not load the results"
          description="The PC did not answer. Try again in a moment."
          action={
            <Button size="m" onClick={() => void fetchIt()}>
              Try again
            </Button>
          }
        >
          <span className="big">🏮</span>
        </Placeholder>
      </div>
    );
  }
  const d = load.data;
  if (d.empty) {
    return (
      <div className="center">
        <Placeholder
          header="No China search yet"
          description="Results of your last /china search show here for 24 hours. In the chat, send /china and what you want — e.g. /china GaN charger 65W EU plug."
        >
          <span className="big">🏮</span>
        </Placeholder>
      </div>
    );
  }

  const pick = d.results.find((r) => r.pick);
  return (
    <div className="page">
      <List>
        <Section
          header={d.kind === "photo" ? "China photo search" : "China search"}
          footer={`Searched ${d.sent} · kept 24 h · most trusted first, then cheapest to Yerevan`}
        >
          <Cell multiline subtitle={d.query_cn ?? undefined}>
            {d.query}
          </Cell>
          {d.sites.map((s) => (
            <Cell key={s.site} multiline subtitle={s.line}>
              {s.name}
            </Cell>
          ))}
        </Section>

        {pick && (
          <Section header="🏆 Pick">
            <Cell multiline subtitle={d.pick_reason ?? undefined}>
              {pick.n}. {pick.title}
            </Cell>
          </Section>
        )}

        {d.results.map((c) => (
          <ResultCard key={c.n} job={d.job} c={c} />
        ))}
      </List>
    </div>
  );
}

function Lines(props: { items: (string | null | undefined)[] }) {
  const items = props.items.filter((x): x is string => !!x);
  if (!items.length) return null;
  return (
    <div className="lines">
      {items.map((x, i) => (
        <div key={i}>{x}</div>
      ))}
    </div>
  );
}

function ResultCard(props: { job: string; c: ChinaCard }) {
  const { job, c } = props;
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<"" | "watch" | "reviews">("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [done, setDone] = useState<{ watch?: boolean; reviews?: boolean }>({});

  const act = async (action: "watch" | "reviews") => {
    setBusy(action);
    setMsg(null);
    const r = await post<ActionReply>("/api/china/action", { action, job, n: c.n });
    setBusy("");
    const tg = webApp();
    if (r.kind === "ok") {
      const where = action === "reviews" && r.data.ok ? " The answer arrives in the bot chat." : "";
      setMsg({ ok: r.data.ok, text: r.data.message + where });
      if (r.data.ok) setDone((x) => ({ ...x, [action]: true }));
      tg?.HapticFeedback?.notificationOccurred(r.data.ok ? "success" : "warning");
    } else {
      setMsg({
        ok: false,
        text:
          r.kind === "slow"
            ? "Too many requests — wait a minute."
            : r.kind === "private"
              ? "This app is private."
              : r.kind === "expired"
                ? "Session expired — close the app and open it again."
                : "The PC did not answer — try again.",
      });
      tg?.HapticFeedback?.notificationOccurred("error");
    }
  };

  const openLink = () => {
    if (!c.link) return;
    const tg = webApp();
    if (tg) tg.openLink(c.link);
    else window.open(c.link, "_blank", "noopener,noreferrer");
  };

  const rv = c.reviews;
  return (
    <Section header={`${c.n}. ${c.site_name}${c.pick ? " · 🏆 pick" : ""}`}>
      <Cell multiline subtitle={c.seller + (c.trust !== null ? ` · 🛡 ${c.trust}` : "")} description={c.title_cn}>
        {c.title}
      </Cell>
      {/* What it costs at the door is the headline; the listing price sits under it
          (review 2026-11-10, decision 099). Both are finished strings from the PC. */}
      <Cell multiline subtitle={c.total ? `Item ${c.price}` : "No delivered total (no price or no route)"}>
        {c.total ? `Delivered ${c.total}` : c.price}
      </Cell>
      {(c.notes.length > 0 || c.flags.length > 0) && (
        <div className="card-notes">
          <Lines items={[...c.notes, ...c.flags.map((f) => "⚠️ " + f)]} />
        </div>
      )}
      <Cell onClick={() => setOpen((o) => !o)} after={<span className="hint">{open ? "▴" : "▾"}</span>}>
        Details
      </Cell>
      {open && (
        <div className="details">
          <Lines items={[c.variant ? `Variant: ${c.variant}` : null, c.delivery]} />
          <Lines items={c.weight} />
          <div className="label">Shipping to Yerevan</div>
          <Lines items={c.routes} />
          <Lines items={[c.trust_line]} />
          <Lines
            items={[
              c.sales ? `Sold: ${c.sales}` : null,
              c.min_order ? `Minimum order: ${c.min_order}` : null,
              c.material ? `Material: ${c.material}` : null,
              c.size ? `Size: ${c.size}` : null,
            ]}
          />
          {c.specs.length > 0 && (
            <>
              <div className="label">Specs</div>
              <Lines items={c.specs} />
            </>
          )}
          {rv.read ? (
            <>
              <div className="label">Reviews{rv.count ? ` (${rv.count})` : ""}</div>
              <Lines items={rv.liked.map((x) => "👍 " + x)} />
              <Lines
                items={rv.complaints.length ? rv.complaints.map((x) => "👎 " + x) : ["👎 no complaints found in the reviews read"]}
              />
            </>
          ) : rv.count ? (
            <Lines items={[`💬 ${rv.count} reviews — not read yet`]} />
          ) : null}
          {c.why && <div className="why">{c.why}</div>}
          {c.ask_seller && (
            <>
              <div className="label">Ask the seller (weight and size)</div>
              <div className="copy">{c.ask_seller}</div>
            </>
          )}
        </div>
      )}
      <div className="actions">
        {c.link && (
          <Button size="s" mode="bezeled" onClick={openLink}>
            Open on {c.site_name}
          </Button>
        )}
        {c.can_watch && (
          <Button size="s" mode="bezeled" loading={busy === "watch"} disabled={!!busy || done.watch} onClick={() => void act("watch")}>
            {done.watch ? "👁 Watching" : "👁 Watch"}
          </Button>
        )}
        {c.can_reviews && (
          <Button size="s" mode="bezeled" loading={busy === "reviews"} disabled={!!busy || done.reviews} onClick={() => void act("reviews")}>
            {done.reviews ? "💬 Reading…" : "💬 Reviews"}
          </Button>
        )}
      </div>
      {msg && <div className={msg.ok ? "msg ok" : "msg bad"}>{msg.text}</div>}
    </Section>
  );
}
