import { Button, Cell, List, Placeholder, Section, TabsList } from "@telegram-apps/telegram-ui";
import { useState } from "react";

import type { Result } from "./api";
import { Field, Notice, RunButton, openLink, useAction, useLoad, Waiting } from "./common";
import type { Basket } from "./types";

// Basket: the last priced shopping list (Yerevan City + Parma), run it again, price one product.
export function BasketScreen(props: { onFail: (r: Result<unknown>) => void }) {
  const [kind, setKind] = useState<"weekly" | "monthly">("weekly");
  const { state, reload } = useLoad<Basket>(`/api/basket/${kind}`, props.onFail);
  const run = useAction();
  const price = useAction();
  const [product, setProduct] = useState("");

  const body =
    state.kind !== "ok" ? null : state.data.empty ? (
      <Section>
        <Placeholder header="No basket priced yet" description="Tap “Price it now” — it takes about 2 minutes.">
          <span className="big">🧺</span>
        </Placeholder>
      </Section>
    ) : (
      <>
        <Section
          header={`${kind === "weekly" ? "This week's list" : "Monthly staples"} · priced ${state.data.when}`}
          footer={state.data.partial ? "Partial: some items could not be priced." : undefined}
        >
          <Cell multiline subtitle={state.data.compare ?? undefined}>
            <b>Total {state.data.total}</b>
          </Cell>
        </Section>
        {state.data.groups.map((g) => (
          <Section key={g.shop} header={`${g.dot} ${g.name}${g.subtotal ? ` · ${g.subtotal}` : ""}`}>
            {g.items.map((i) => (
              <Cell
                key={i.item + i.product}
                multiline
                subtitle={`${i.buy}${i.product ? ` · ${i.product}` : ""}`}
                after={<span className="hint">{i.cost}</span>}
                onClick={i.url ? () => openLink(i.url as string) : undefined}
              >
                {i.item}
              </Cell>
            ))}
          </Section>
        ))}
        {(state.data.unpriced.length > 0 || state.data.skipped.length > 0) && (
          <Section header="Not priced">
            {state.data.unpriced.map((x) => (
              <Cell key={x} subtitle="no match at either shop">
                {x}
              </Cell>
            ))}
            {state.data.skipped.map((x) => (
              <Cell key={x} subtitle="skipped">
                {x}
              </Cell>
            ))}
          </Section>
        )}
      </>
    );

  return (
    <div className="page">
      <List>
        <TabsList>
          <TabsList.Item selected={kind === "weekly"} onClick={() => setKind("weekly")}>
            Weekly
          </TabsList.Item>
          <TabsList.Item selected={kind === "monthly"} onClick={() => setKind("monthly")}>
            Monthly
          </TabsList.Item>
        </TabsList>

        <Section footer="The bot prices the list at both shops (about 2 minutes), fills the checklist and sends it to both of you.">
          <div className="actions">
            <RunButton job="basket" args={kind} label={`🧺 Price the ${kind} list now`} action={run} />
          </div>
          <Notice msg={run.msg} />
        </Section>

        {state.kind !== "ok" ? <Waiting state={state} onRetry={() => void reload()} icon="🧺" /> : body}

        <Section header="Price check" footer="One product at both shops, cheapest first. English or Armenian.">
          <Field
            header="Product"
            value={product}
            onChange={setProduct}
            placeholder="lentils, ոսպ, olive oil parma"
            onEnter={() => void price.send("/api/run", { job: "price", args: product })}
          />
          <div className="actions">
            <Button
              size="m"
              loading={price.busy}
              disabled={price.busy || product.trim().length < 2}
              onClick={() => void price.send("/api/run", { job: "price", args: product })}
            >
              🔍 Check prices
            </Button>
          </div>
          <Notice msg={price.msg} />
        </Section>
      </List>
    </div>
  );
}
