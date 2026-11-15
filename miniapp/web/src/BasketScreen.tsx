import { Button, Cell, List, Placeholder, Section, TabsList } from "@telegram-apps/telegram-ui";
import { useState } from "react";

import type { Result } from "./api";
import { Field, Notice, RunButton, openLink, useAction, useLoad, Waiting } from "./common";
import { useClosingConfirmation, useMainButton, usePref } from "./hooks";
import { confirmAsk, haptic } from "./telegram";
import type { Basket } from "./types";

const KINDS = ["weekly", "monthly"] as const;

// Basket: the last priced shopping list (Yerevan City + Parma), run it again, price one product.
export function BasketScreen(props: { onFail: (r: Result<unknown>) => void }) {
  const [kind, setKind, ready] = usePref("basket_kind", KINDS, "weekly");
  const { state, reload } = useLoad<Basket>(ready ? `/api/basket/${kind}` : null, props.onFail);
  const run = useAction();
  const price = useAction();
  const [product, setProduct] = useState("");
  useClosingConfirmation(product.trim().length > 0);

  // The list goes to BOTH chats, so it is asked first. The screen's main action lives in
  // Telegram's bottom bar (MainButton); an in-page button stands in where there is none.
  const ASK = `Price the ${kind} list at both shops? It takes about 2 minutes and the list is sent to both of you.`;
  const runBasket = async () => {
    if (!(await confirmAsk(ASK))) return;
    haptic("tap");
    await run.send("/api/run", { job: "basket", args: kind });
  };
  const mainButton = useMainButton({
    text: `🧺 Price the ${kind} list now`,
    visible: ready,
    active: !run.busy,
    loading: run.busy,
    onClick: () => void runBasket(),
  });

  const body =
    state.kind !== "ok" ? null : state.data.empty ? (
      <Section>
        <Placeholder header="No basket priced yet" description="Price it now — it takes about 2 minutes.">
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
                after={<span className="hint nowrap">{i.cost}</span>}
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
          {KINDS.map((k) => (
            <TabsList.Item
              key={k}
              selected={kind === k}
              onClick={() => {
                if (k !== kind) haptic("select");
                setKind(k);
              }}
            >
              {k === "weekly" ? "Weekly" : "Monthly"}
            </TabsList.Item>
          ))}
        </TabsList>

        <Section footer="The bot prices the list at both shops (about 2 minutes), fills the checklist and sends it to both of you.">
          {!mainButton && (
            <div className="actions">
              <RunButton job="basket" args={kind} label={`🧺 Price the ${kind} list now`} action={run} confirm={ASK} />
            </div>
          )}
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
