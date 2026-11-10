import { Button, Cell, List, Placeholder, Section, Spinner, TabsList } from "@telegram-apps/telegram-ui";
import { useCallback, useEffect, useRef, useState } from "react";

import { get, post, type ActionReply, type China, type ChinaCard, type Result } from "./api";
import { Field, Notice, useAction } from "./common";
import { webApp } from "./telegram";
import type { ChinaStatus } from "./types";

// Step 1 (docs/briefs/MINI_APP.md §12): the person's latest /china result. Every number is a
// finished string from the PC (miniapp/china_view.py); this file only lays it out.

type Load = { kind: "loading" } | { kind: "ok"; data: China } | { kind: "failed" };

const SITES = [
  ["", "All"],
  ["pinduoduo", "PDD"],
  ["taobao", "Taobao"],
  ["1688", "1688"],
] as const;
const POLL_MS = 8000;
const SETTLE_MS = 15000; // the bot needs a moment to pick the request up before "idle" means done

export function ChinaScreen(props: { onFail: (r: Result<unknown>) => void }) {
  const { onFail } = props;
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const [status, setStatus] = useState<ChinaStatus | null>(null);
  const [submittedAt, setSubmittedAt] = useState<number | null>(null);
  const [outcome, setOutcome] = useState<string>("");
  const jobBefore = useRef<string | null>(null);

  const fetchIt = useCallback(async (): Promise<string | null> => {
    const r = await get<China>("/api/china");
    if (r.kind === "ok") {
      setLoad({ kind: "ok", data: r.data });
      return r.data.empty ? null : r.data.job;
    }
    if (r.kind === "private" || r.kind === "expired") onFail(r);
    else setLoad({ kind: "failed" });
    return null;
  }, [onFail]);

  const pollStatus = useCallback(async () => {
    const r = await get<ChinaStatus>("/api/china/status");
    if (r.kind === "ok") setStatus(r.data);
    return r.kind === "ok" ? r.data : null;
  }, []);

  useEffect(() => {
    void fetchIt();
    void pollStatus();
  }, [fetchIt, pollStatus]);

  const busy = !!status && (status.running || status.waiting > 0);
  const watching = submittedAt !== null || busy;
  useEffect(() => {
    if (!watching) return;
    const id = window.setInterval(async () => {
      const st = await pollStatus();
      if (!st || st.running || st.waiting > 0) return;
      if (submittedAt !== null && Date.now() - submittedAt < SETTLE_MS) return;
      const job = await fetchIt();
      setSubmittedAt(null);
      setOutcome(
        job && job !== jobBefore.current
          ? "Done — the new results are below."
          : "No new results yet. If the bot asked you a question, answer it in the chat.",
      );
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [watching, submittedAt, pollStatus, fetchIt]);

  const d = load.kind === "ok" ? load.data : null;
  const results = d && !d.empty ? d : null;
  const pick = results?.results.find((r) => r.pick);

  const started = () => {
    jobBefore.current = results ? results.job : null;
    setOutcome("");
    setSubmittedAt(Date.now());
  };

  return (
    <div className="page">
      <List>
        <SearchForm
          busy={busy || submittedAt !== null}
          outcome={outcome}
          status={status}
          onStarted={started}
        />

        {load.kind === "loading" && (
          <div className="center short">
            <Spinner size="l" />
          </div>
        )}
        {load.kind === "failed" && (
          <Section>
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
          </Section>
        )}
        {d && d.empty && (
          <Section>
            <Placeholder
              header="No China search yet"
              description="Type what you want above. Results of your last search stay here for 24 hours."
            >
              <span className="big">🏮</span>
            </Placeholder>
          </Section>
        )}
        {results && (
          <>
            <Section
              header={results.kind === "photo" ? "China photo search" : "China search"}
              footer={`Searched ${results.sent} · kept 24 h · most trusted first, then cheapest to Yerevan`}
            >
              <Cell multiline subtitle={results.query_cn ?? undefined}>
                {results.query}
              </Cell>
              {results.sites.map((s) => (
                <Cell key={s.site} multiline subtitle={s.line}>
                  {s.name}
                </Cell>
              ))}
            </Section>

            {pick && (
              <Section header="🏆 Pick">
                <Cell multiline subtitle={results.pick_reason ?? undefined}>
                  {pick.n}. {pick.title}
                </Cell>
              </Section>
            )}

            {results.results.map((c) => (
              <ResultCard key={c.n} job={results.job} c={c} />
            ))}
          </>
        )}
      </List>
    </div>
  );
}

function SearchForm(props: {
  busy: boolean;
  outcome: string;
  status: ChinaStatus | null;
  onStarted: () => void;
}) {
  const [text, setText] = useState("");
  const [site, setSite] = useState<string>("");
  const act = useAction();
  const args = site ? `only ${site} ${text.trim()}` : text.trim();
  const submit = async () => {
    if (await act.send("/api/run", { job: "china", args })) {
      setText("");
      props.onStarted();
    }
  };
  const st = props.status;
  const running = st
    ? st.running
      ? `A China search is running${st.waiting ? ` · ${st.waiting} of yours waiting` : ""}.`
      : st.waiting
        ? `${st.waiting} of your searches waiting.`
        : ""
    : "";
  return (
    <Section
      header="Search China"
      footer="PDD = Pinduoduo. Pinduoduo and 1688 are read automatically (about 5 minutes); Taobao gets a search link. If the bot needs to ask you something it asks in the chat. For a photo search, send the photo to the bot."
    >
      <Field
        header="What are you looking for?"
        value={text}
        onChange={setText}
        placeholder="GaN charger 65W EU plug"
        onEnter={() => void submit()}
      />
      <TabsList>
        {SITES.map(([id, label]) => (
          <TabsList.Item key={id} selected={site === id} onClick={() => setSite(id)}>
            {label}
          </TabsList.Item>
        ))}
      </TabsList>
      <div className="actions">
        <Button
          size="m"
          loading={act.busy}
          disabled={act.busy || props.busy || text.trim().length < 3}
          onClick={() => void submit()}
        >
          🔎 Search
        </Button>
      </div>
      {props.busy && !running && <div className="msg ok">Searching… results appear here by themselves.</div>}
      {running && <div className="msg ok">{running} Results appear here by themselves.</div>}
      {props.outcome && <div className="msg ok">{props.outcome}</div>}
      <Notice msg={act.msg} />
    </Section>
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
