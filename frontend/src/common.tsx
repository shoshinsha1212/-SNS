import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type FlagTarget, type Meta } from "./api";

export const MetaContext = createContext<Meta | null>(null);
export const useMeta = () => useContext(MetaContext);

export const pct = (r: number | null | undefined) => (r == null ? "—" : `${Math.round(r * 100)}%`);

/** 非同期に読み込む値と、そのエラー。reload で読み直す。 */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setError(null);
    fn()
      .then((d) => alive && setData(d))
      .catch((e: Error) => alive && setError(e.message));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { data, error, reload: () => setTick((t) => t + 1), setData };
}

/** 無料サーバーはしばらく使われないと止まり、起こすのに最大1分ほどかかる。長引いたらそれを伝える。 */
const SLOW_MS = 4000;

export function Loading({ error }: { error?: string | null }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const t = window.setTimeout(() => setSlow(true), SLOW_MS);
    return () => window.clearTimeout(t);
  }, []);
  if (error) return <div className="card error">{error}</div>;
  return (
    <div className="loading" role="status">
      <div className="row center">
        <span className="spinner" aria-hidden /> 読み込み中…
      </div>
      {slow && (
        <p className="small muted">
          サーバーを起動しています。しばらく使われていなかったため、表示まで最大1分ほどかかります。このままお待ちください。
        </p>
      )}
    </div>
  );
}

export const VOTE_LABEL: Record<number, string> = { 1: "賛成", [-1]: "反対", 0: "わからない" };

export function VoteChip({ value }: { value: number | null }) {
  if (value == null) return <span className="chip muted">未回答</span>;
  const cls = value === 1 ? "agree" : value === -1 ? "disagree" : "pass";
  return <span className={`chip ${cls}`}>あなた：{VOTE_LABEL[value]}</span>;
}

export function PrivacyNote() {
  return <p className="note">個人や所属（大学名・サークル名・実名など）が特定される内容は書かないでください。</p>;
}

/** 通報ボタン。一度押したら「通報済み」になる。 */
export function FlagButton({ type, id, onHidden, label = "通報" }: { type: FlagTarget; id: number; onHidden?: () => void; label?: string }) {
  const [state, setState] = useState<"idle" | "sending" | "done">("idle");
  if (state === "done") return <span className="flag done">通報しました</span>;
  return (
    <button
      type="button"
      className="flag"
      disabled={state === "sending"}
      aria-label="不適切な内容として通報"
      onClick={async () => {
        if (!window.confirm("不適切な内容として通報しますか？一定数の通報で自動的に非表示になります。")) return;
        setState("sending");
        try {
          const r = await api.flag(type, id);
          setState("done");
          if (r.hidden) onHidden?.();
        } catch {
          setState("idle");
        }
      }}
    >
      ⚑ {label}
    </button>
  );
}

export function Collapse({ label, children, onOpen }: { label: ReactNode; children: ReactNode; onOpen?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="collapse">
      <button
        type="button"
        className="link"
        aria-expanded={open}
        onClick={() => {
          if (!open) onOpen?.();
          setOpen(!open);
        }}
      >
        {open ? "▾" : "▸"} {label}
      </button>
      {open && <div className="collapse-body">{children}</div>}
    </div>
  );
}
