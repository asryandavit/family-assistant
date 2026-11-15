import { List, Placeholder, Section, TabsList } from "@telegram-apps/telegram-ui";

import type { Result } from "./api";
import { Blocks, useLoad, Waiting } from "./common";
import { usePref } from "./hooks";
import { haptic } from "./telegram";
import type { Page } from "./types";

// Today · Meals · Training · Week: the chat's own text for you (coach/plan_text.py), as blocks.
const TABS = [
  ["today", "Today"],
  ["meals", "Meals"],
  ["training", "Training"],
  ["week", "Week"],
] as const;
const NAMES = TABS.map(([id]) => id);

export function PlanScreen(props: { onFail: (r: Result<unknown>) => void }) {
  // the tab you used last is remembered per person (CloudStorage); nothing but the tab name
  const [name, setName, ready] = usePref("plan_tab", NAMES, "today");
  const { state, reload } = useLoad<Page>(ready ? `/api/plan/${name}` : null, props.onFail);
  return (
    <div className="page">
      <List>
        <TabsList>
          {TABS.map(([id, label]) => (
            <TabsList.Item
              key={id}
              selected={id === name}
              onClick={() => {
                if (id !== name) haptic("select");
                setName(id);
              }}
            >
              {label}
            </TabsList.Item>
          ))}
        </TabsList>
        {state.kind !== "ok" ? (
          <Waiting state={state} onRetry={() => void reload()} icon="📅" />
        ) : state.data.unreadable ? (
          <Section>
            <Placeholder
              header="The plan could not be read"
              description="The plan files on the PC did not open just now. The Drive copy is linked in the bot's Today."
            >
              <span className="big">📅</span>
            </Placeholder>
          </Section>
        ) : (
          <Section header={state.data.title}>
            <Blocks blocks={state.data.blocks} />
          </Section>
        )}
      </List>
    </div>
  );
}
