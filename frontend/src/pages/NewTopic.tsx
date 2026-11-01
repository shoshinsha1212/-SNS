import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { PrivacyNote, useMeta } from "../common";

type Draft = { body: string; axis: string; direction: "" | "1" | "-1" };
const empty = (): Draft => ({ body: "", axis: "", direction: "" });

export default function NewTopic() {
  const meta = useMeta();
  const nav = useNavigate();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [rows, setRows] = useState<Draft[]>([empty(), empty(), empty()]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const filled = rows.filter((r) => r.body.trim().length >= 5);
  const canSubmit = title.trim().length >= 3 && filled.length >= 3 && !busy;
  const update = (i: number, patch: Partial<Draft>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const statements = filled.map((r) => ({
        body: r.body,
        axis_key: r.axis && r.direction ? r.axis : null,
        direction: r.axis && r.direction ? (Number(r.direction) as 1 | -1) : null,
      }));
      const { id } = await api.createTopic(title, description, statements);
      nav(`/t/${id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  return (
    <>
      <h1>議題を作る</h1>
      <p className="muted">タイトルと、賛成・反対で答えられる論点が3つあれば作れます。作った議題はすぐに一覧に出ます。</p>
      <div className="card">
        <label className="field">
          <span>タイトル（3〜60字）</span>
          <input value={title} maxLength={60} onChange={(e) => setTitle(e.target.value)} placeholder="例：大学の授業はオンラインで十分か" />
        </label>
        <label className="field">
          <span>説明（任意・300字まで）</span>
          <textarea rows={2} maxLength={300} value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
      </div>

      <h2>論点（3つ以上）</h2>
      {rows.map((r, i) => {
        const axis = meta?.axes.find((a) => a.key === r.axis);
        return (
          <div className="card" key={i}>
            <label className="field">
              <span>論点 {i + 1}（5〜100字）</span>
              <textarea rows={2} maxLength={100} value={r.body} onChange={(e) => update(i, { body: e.target.value })} placeholder="例：講義はオンラインでも学びの質は変わらない" />
            </label>
            <details>
              <summary className="small">価値観マップに使う（任意）</summary>
              <p className="small muted">この論点に賛成した人が、どの価値観の軸のどちら側に寄るかを選びます。分からなければ空のままで大丈夫です（運営があとで付けることがあります）。</p>
              <div className="row wrap-gap">
                <select value={r.axis} onChange={(e) => update(i, { axis: e.target.value, direction: "" })} aria-label="価値観の軸">
                  <option value="">軸を選ばない</option>
                  {meta?.axes.map((a) => (
                    <option key={a.key} value={a.key}>
                      {a.name}
                    </option>
                  ))}
                </select>
                {axis && (
                  <select value={r.direction} onChange={(e) => update(i, { direction: e.target.value as Draft["direction"] })} aria-label="賛成するとどちら寄りか">
                    <option value="">賛成すると…</option>
                    <option value="-1">「{axis.left}」寄り</option>
                    <option value="1">「{axis.right}」寄り</option>
                  </select>
                )}
              </div>
            </details>
            {rows.length > 3 && (
              <button type="button" className="link small" onClick={() => setRows(rows.filter((_, j) => j !== i))}>
                この論点を消す
              </button>
            )}
          </div>
        );
      })}
      {rows.length < 10 && (
        <button type="button" className="btn ghost small" onClick={() => setRows([...rows, empty()])}>
          ＋ 論点を増やす
        </button>
      )}
      <PrivacyNote />
      {error && <p className="error-text">{error}</p>}
      <div className="row">
        <button className="btn primary" disabled={!canSubmit} onClick={submit}>
          議題を公開する
        </button>
        {!canSubmit && !busy && <span className="small muted">タイトルと5字以上の論点が3つ必要です</span>}
      </div>
    </>
  );
}
