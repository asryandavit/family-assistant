import { Button, Cell, List, Placeholder, Section } from "@telegram-apps/telegram-ui";
import { useState } from "react";

import type { Result } from "./api";
import { Field, Notice, RunButton, openLink, useAction, useLoad, Waiting } from "./common";
import type { Travel } from "./types";

// Travel: the latest flight and stay results from the daily scan, a scan on demand, and the
// /flights and /stays searches as forms (the bot runs them; results arrive in the chat).
export function TravelScreen(props: { onFail: (r: Result<unknown>) => void }) {
  const { state, reload } = useLoad<Travel>("/api/travel", props.onFail);
  const scan = useAction();
  if (state.kind !== "ok") return <Waiting state={state} onRetry={() => void reload()} icon="✈️" />;
  const t = state.data;
  return (
    <div className="page">
      <List>
        <Section
          header="Daily scan"
          footer={
            t.scan
              ? `${t.scan.enabled ? "On" : "Paused"} · last ${t.scan.last ?? "—"} · next ${t.scan.next ?? "—"}`
              : undefined
          }
        >
          <div className="actions">
            <RunButton job="scan" label="✈️ Scan now" action={scan} />
            <RunButton job="digest" label="📊 Send digest" action={scan} />
          </div>
          <Notice msg={scan.msg} />
        </Section>

        {t.unavailable && (
          <Section>
            <Placeholder header="No scan results to show" description="Google Sheets did not answer. Try again in a minute.">
              <span className="big">✈️</span>
            </Placeholder>
          </Section>
        )}

        {t.trips.length > 0 && (
          <Section header={`Cheapest trips · scan of ${t.run_date}`} footer="Return trip, total for everyone in the party; club = with the Wizz Discount Club.">
            {t.trips.map((x, i) => (
              <Cell
                key={i}
                multiline
                subtitle={`${x.out} → ${x.back} · ${x.nights} nights · ${x.pax}`}
                after={
                  <span className="hint">
                    {x.total} {x.currency}
                    {x.club ? ` (club ${x.club})` : ""}
                  </span>
                }
              >
                {x.route}
              </Cell>
            ))}
          </Section>
        )}

        {t.stays.length > 0 && (
          <Section header={`Best stays · scan of ${t.stays_date}`}>
            {t.stays.map((s, i) => (
              <Cell
                key={i}
                multiline
                subtitle={`${s.city} · ${s.in} → ${s.out} (${s.nights} nights) · ${s.source} · rating ${s.rating}`}
                description={s.why}
                after={
                  <span className="hint">
                    {s.total} {s.currency}
                  </span>
                }
                onClick={s.url ? () => openLink(s.url as string) : undefined}
              >
                {s.name}
              </Cell>
            ))}
          </Section>
        )}

        <FlightsForm />
        <StaysForm />
      </List>
    </div>
  );
}

function FlightsForm() {
  const [where, setWhere] = useState("");
  const [when, setWhen] = useState("");
  const [nights, setNights] = useState("7");
  const act = useAction();
  const args = [where.trim(), when.trim(), nights.trim()].filter(Boolean).join(" ");
  const go = () => void act.send("/api/run", { job: "flights", args });
  return (
    <Section header="Search flights" footer="Dates as a window, e.g. 01-30.11 or 20.12-05.01. The bot searches (1–3 min) and sends the results to the chat.">
      <Field header="Where to (code or city)" value={where} onChange={setWhere} placeholder="BUD" />
      <Field header="When" value={when} onChange={setWhen} placeholder="01-30.11" />
      <Field header="Nights" value={nights} onChange={setNights} placeholder="7 or 5-7" onEnter={go} />
      <div className="actions">
        <Button size="m" loading={act.busy} disabled={act.busy || !where.trim() || !when.trim()} onClick={go}>
          🔎 Search flights
        </Button>
      </div>
      <Notice msg={act.msg} />
    </Section>
  );
}

function StaysForm() {
  const [where, setWhere] = useState("");
  const [when, setWhen] = useState("");
  const [words, setWords] = useState("");
  const act = useAction();
  const args = [where.trim(), when.trim(), words.trim()].filter(Boolean).join(" ");
  const go = () => void act.send("/api/run", { job: "stays", args });
  return (
    <Section header="Search stays" footer="Keywords: sea center quiet pool breakfast apt hotel strict budget90. The results arrive in the chat (2–4 min).">
      <Field header="City or airport code" value={where} onChange={setWhere} placeholder="LCA" />
      <Field header="Check-in – check-out" value={when} onChange={setWhen} placeholder="04-11.11" />
      <Field header="Keywords, optional" value={words} onChange={setWords} placeholder="sea center" onEnter={go} />
      <div className="actions">
        <Button size="m" loading={act.busy} disabled={act.busy || !where.trim() || !when.trim()} onClick={go}>
          🏨 Search stays
        </Button>
      </div>
      <Notice msg={act.msg} />
    </Section>
  );
}
