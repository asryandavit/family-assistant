import { Button, Cell, Input, Placeholder, Spinner } from "@telegram-apps/telegram-ui";
import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";

import { get, post, type Result } from "./api";
import type { Block, Reply, Seg } from "./types";
import { confirmAsk, haptic, webApp } from "./telegram";

export function openLink(url: string) {
  const tg = webApp();
  if (tg) tg.openLink(url);
  else window.open(url, "_blank", "noopener,noreferrer");
}

// ---- loading a GET once, with a retry state

export type Loaded<T> =
  | { kind: "loading" }
  | { kind: "ok"; data: T }
  | { kind: "failed" };

// path null = not yet (the screen is still reading a stored preference): stays "loading".
export function useLoad<T>(path: `/api/${string}` | null, onFail: (r: Result<unknown>) => void) {
  const [state, setState] = useState<Loaded<T>>({ kind: "loading" });
  const failRef = useRef(onFail);
  failRef.current = onFail;
  const reload = useCallback(async () => {
    if (!path) return;
    const r = await get<T>(path);
    if (r.kind === "ok") setState({ kind: "ok", data: r.data });
    else if (r.kind === "private" || r.kind === "expired") failRef.current(r);
    else setState({ kind: "failed" });
  }, [path]);
  useEffect(() => {
    setState({ kind: "loading" });
    void reload();
  }, [reload]);
  return { state, reload };
}

export function Waiting(props: { state: Loaded<unknown>; onRetry: () => void; icon: string }) {
  if (props.state.kind === "loading") {
    return (
      <div className="center">
        <Spinner size="l" />
      </div>
    );
  }
  return (
    <div className="center">
      <Placeholder
        header="Could not load this"
        description="The PC did not answer. Try again in a moment."
        action={
          <Button size="m" onClick={props.onRetry}>
            Try again
          </Button>
        }
      >
        <span className="big">{props.icon}</span>
      </Placeholder>
    </div>
  );
}

// ---- running a chat command or an edit; one message under the form

export type Msg = { ok: boolean; text: string } | null;

export function useAction() {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<Msg>(null);
  const send = useCallback(async (path: `/api/${string}`, body: object): Promise<boolean> => {
    setBusy(true);
    setMsg(null);
    const r = await post<Reply>(path, body);
    setBusy(false);
    if (r.kind === "ok") {
      setMsg({ ok: r.data.ok, text: r.data.message });
      haptic(r.data.ok ? "ok" : "warn");
      return r.data.ok;
    }
    const text =
      r.kind === "slow"
        ? "Too many requests — wait a minute."
        : r.kind === "expired"
          ? "Session expired — close and reopen the app."
          : r.kind === "private"
            ? "This app is private."
            : "The PC did not answer — try again.";
    setMsg({ ok: false, text });
    haptic("error");
    return false;
  }, []);
  return { busy, msg, send, clear: () => setMsg(null) };
}

export function Notice(props: { msg: Msg }) {
  if (!props.msg) return null;
  return <div className={props.msg.ok ? "msg ok" : "msg bad"}>{props.msg.text}</div>;
}

// A command the bot runs (its answer arrives in the chat): one button.
export function RunButton(props: {
  job: string;
  args?: string;
  label: string;
  action: ReturnType<typeof useAction>;
  mode?: "bezeled" | "filled" | "outline";
  // ask first (a native popup) for an action whose result goes to the whole family
  confirm?: string;
}) {
  const { job, args, label, action, mode, confirm } = props;
  const go = async () => {
    if (confirm && !(await confirmAsk(confirm))) return;
    haptic("tap");
    await action.send("/api/run", args === undefined ? { job } : { job, args });
  };
  return (
    <Button size="s" mode={mode ?? "bezeled"} loading={action.busy} disabled={action.busy} onClick={() => void go()}>
      {label}
    </Button>
  );
}

// A form field. Enter submits.
export function Field(props: {
  header: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  onEnter?: () => void;
  after?: ReactNode;
}) {
  const id = useId();
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        {props.header}
      </label>
      <Input
        id={id}
        placeholder={props.placeholder}
        value={props.value}
        maxLength={200}
        after={props.after}
        onChange={(e) => props.onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") props.onEnter?.();
        }}
      />
    </div>
  );
}

// ---- blocks from the chat's own text

function Segs({ s }: { s: Seg[] }) {
  return (
    <>
      {s.map((x, i) => {
        let el: ReactNode = x.t;
        if (x.c) el = <code>{el}</code>;
        if (x.i) el = <i>{el}</i>;
        if (x.b) el = <b>{el}</b>;
        if (x.a) {
          const url = x.a;
          el = (
            <a
              href={url}
              onClick={(e) => {
                e.preventDefault();
                openLink(url);
              }}
            >
              {el}
            </a>
          );
        }
        return <span key={i}>{el}</span>;
      })}
    </>
  );
}

export function Blocks(props: { blocks: Block[] }) {
  return (
    <div className="page-text">
      {props.blocks.map((b, i) =>
        b.k === "p" ? (
          <p key={i}>
            <Segs s={b.s} />
          </p>
        ) : (
          <Fold key={i} title={b.title} lines={b.b} />
        ),
      )}
    </div>
  );
}

function Fold(props: { title: string; lines: { k: "p"; s: Seg[] }[] }) {
  const [open, setOpen] = useState(/today/i.test(props.title));
  return (
    <div className="fold">
      <Cell multiline onClick={() => setOpen((o) => !o)} after={<span className="hint">{open ? "▴" : "▾"}</span>}>
        {props.title || "More"}
      </Cell>
      {open &&
        props.lines.map((l, i) => (
          <p key={i}>
            <Segs s={l.s} />
          </p>
        ))}
    </div>
  );
}

export { Input };
