import { Button, Cell, List, Placeholder, Section } from "@telegram-apps/telegram-ui";
import { useState } from "react";

import type { Result } from "./api";
import { Field, Notice, RunButton, openLink, useAction, useLoad, Waiting } from "./common";
import type { Market, MarketItem } from "./types";

// Market watch (docs/briefs/MARKET_WATCH.md): the list, mark bought / remove, add by link,
// "Check prices now" (the bot runs the job and the report arrives in the chat).
export function MarketScreen(props: { onFail: (r: Result<unknown>) => void }) {
  const { state, reload } = useLoad<Market>("/api/market", props.onFail);
  const check = useAction();
  if (state.kind !== "ok") return <Waiting state={state} onRetry={() => void reload()} icon="🌍" />;
  const m = state.data;
  return (
    <div className="page">
      <List>
        <Section
          header={`Watching · ${m.items.length} item${m.items.length === 1 ? "" : "s"}`}
          footer={m.note}
        >
          {m.items.length === 0 && (
            <Placeholder header="Nothing watched yet" description="Add an item below with its store link.">
              <span className="big">🌍</span>
            </Placeholder>
          )}
          {m.items.map((it) => (
            <ItemRow key={it.id} it={it} onChanged={() => void reload()} />
          ))}
          <div className="actions">
            <RunButton job="market" label="🔄 Check prices now" action={check} />
          </div>
          <Notice msg={check.msg} />
        </Section>
        <AddForm stores={m.stores} onAdded={() => void reload()} />
      </List>
    </div>
  );
}

function ItemRow(props: { it: MarketItem; onChanged: () => void }) {
  const { it, onChanged } = props;
  const act = useAction();
  const [confirm, setConfirm] = useState(false);
  const go = async (action: "bought" | "remove") => {
    if (await act.send("/api/market/action", { action, id: it.id })) onChanged();
  };
  return (
    <>
      <Cell
        multiline
        subtitle={`${it.stores.join(", ")}${it.qty > 1 ? ` · ×${it.qty}` : ""}${it.added_by ? ` · ${it.added_by}` : ""}`}
        description={it.best ? `Best: ${it.best}` : "No price read yet — the next check fills it in"}
      >
        {it.n}. {it.name}
        {it.weight_needed ? " ⚖️" : ""}
      </Cell>
      <div className="actions">
        {it.links.slice(0, 2).map((u, i) => (
          <Button key={u} size="s" mode="bezeled" onClick={() => openLink(u)}>
            Open{it.links.length > 1 ? ` ${i + 1}` : ""}
          </Button>
        ))}
        <Button size="s" mode="bezeled" disabled={act.busy} onClick={() => void go("bought")}>
          ✅ Bought
        </Button>
        {confirm ? (
          <Button size="s" mode="filled" loading={act.busy} onClick={() => void go("remove")}>
            Remove for sure?
          </Button>
        ) : (
          <Button size="s" mode="bezeled" onClick={() => setConfirm(true)}>
            🗑 Remove
          </Button>
        )}
      </div>
      {it.weight_needed && <div className="msg hintline">⚖️ Weight needed for totals: send /watch weight {it.n} 2.4 in the chat.</div>}
      <Notice msg={act.msg} />
    </>
  );
}

function AddForm(props: { stores: string[]; onAdded: () => void }) {
  const [name, setName] = useState("");
  const [link, setLink] = useState("");
  const [weight, setWeight] = useState("");
  const act = useAction();
  const submit = async () => {
    const body: { name: string; link: string; weight?: string } = { name, link };
    if (weight.trim()) body.weight = weight;
    if (await act.send("/api/market/add", body)) {
      setName("");
      setLink("");
      setWeight("");
      props.onAdded();
    }
  };
  return (
    <Section header="Add an item" footer={`Stores watched: ${props.stores.join(", ")}. One link per store, the exact item.`}>
      <Field header="Name" value={name} onChange={setName} placeholder="e.g. USB-C cable 2 m" />
      <Field header="Store link (https://…)" value={link} onChange={setLink} placeholder="https://www.amazon.com/dp/…" />
      <Field header="Weight, optional" value={weight} onChange={setWeight} placeholder="0.2 kg" onEnter={() => void submit()} />
      <div className="actions">
        <Button size="m" loading={act.busy} disabled={act.busy || !name.trim() || !link.trim()} onClick={() => void submit()}>
          ➕ Add to the watch list
        </Button>
      </div>
      <Notice msg={act.msg} />
    </Section>
  );
}
