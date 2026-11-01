import { useState } from "react";
import { adminApi, adminKey, type AdminStatement, type Metrics } from "../api";
import { Loading, pct, useLoad, useMeta } from "../common";

const TYPE_LABEL = { topic: "議題", statement: "論点", reason: "理由", story: "体験談" } as const;

function Funnel({ m }: { m: Metrics }) {
  const top = Math.max(1, m.funnel[0]?.users ?? 0);
  return (
    <div className="card">
      <h2>漏斗（人数）</h2>
      <div className="table-scroll">
      <table className="table">
        <thead>
          <tr>
            <th>段階</th>
            <th>人数</th>
            <th>前の段階から</th>
            <th>最初から</th>
            <th>段階を飛ばした人も含む</th>
          </tr>
        </thead>
        <tbody>
          {m.funnel.map((f, i) => {
            const prev = i === 0 ? null : m.funnel[i - 1].users;
            return (
              <tr key={f.key}>
                <td>
                  {f.label}
                  <div className="funnel-bar" style={{ width: `${(f.users / top) * 100}%` }} />
                </td>
                <td>{f.users}</td>
                <td>{prev ? pct(f.users / prev) : "—"}</td>
                <td>{pct(f.users / top)}</td>
                <td>{f.raw}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>
      <p className="small muted">
        「人数」は、その段階までをすべて通った人です。「2議題目を始めた」は2つ以上の議題で1票以上入れた人、「共有した」は価値観マップの共有ボタンを押した人です。
      </p>
    </div>
  );
}

function MetricsView() {
  const m = useLoad(adminApi.metrics, []);
  if (!m.data) return <Loading error={m.error} />;
  const d = m.data;
  return (
    <>
      <div className="row end">
        <button className="btn ghost small" onClick={m.reload}>
          再読み込み
        </button>
      </div>
      <Funnel m={d} />
      <div className="stat-grid">
        <div className="card stat">
          <span className="small muted">7日以内の再訪率</span>
          <strong>{d.return_7d.visitors ? pct(d.return_7d.returned / d.return_7d.visitors) : "—"}</strong>
          <span className="small muted">
            {d.return_7d.returned} / {d.return_7d.visitors}人
          </span>
        </div>
        <div className="card stat">
          <span className="small muted">理解度の平均（1〜5）</span>
          <strong>{d.understanding.avg?.toFixed(2) ?? "—"}</strong>
          <span className="small muted">
            {d.understanding.n}件・分布 {d.understanding.dist.join(" / ")}
          </span>
        </div>
        {(
          [
            ["reasons", "理由のひとこと"],
            ["stories", "体験談"],
            ["story_readers", "体験談を開いた人"],
            ["user_statements", "参加者が足した論点"],
            ["user_topics", "参加者が作った議題"],
            ["flags", "通報"],
          ] as const
        ).map(([k, label]) => (
          <div className="card stat" key={k}>
            <span className="small muted">{label}</span>
            <strong>{d.content[k] ?? 0}</strong>
          </div>
        ))}
      </div>

      <div className="card">
        <h2>議題別</h2>
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>議題</th>
                <th>開いた</th>
                <th>回答</th>
                <th>完答</th>
                <th>完答率</th>
                <th>離脱位置（何問目まで答えて止まったか：人数）</th>
                <th>理解度</th>
              </tr>
            </thead>
            <tbody>
              {d.topics.map((t) => (
                <tr key={t.id} className={t.hidden ? "muted" : ""}>
                  <td>
                    {t.title}
                    {t.origin === "user" && <span className="chip muted">参加者</span>}
                    {t.hidden && <span className="chip muted">非表示</span>}
                  </td>
                  <td>{t.viewers}</td>
                  <td>{t.voters}</td>
                  <td>{t.completers}</td>
                  <td>{t.voters ? pct(t.completers / t.voters) : "—"}</td>
                  <td className="small">{t.dropoff.length ? t.dropoff.map((x) => `${x.answered}/${t.n_statements}問：${x.users}`).join("、") : "—"}</td>
                  <td>{t.understanding_avg != null ? `${t.understanding_avg.toFixed(1)}（${t.understanding_n}）` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h2>日別（直近14日・日本時間）</h2>
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>日付</th>
                <th>訪問</th>
                <th>投票</th>
              </tr>
            </thead>
            <tbody>
              {d.daily.map((x) => (
                <tr key={x.date}>
                  <td>{x.date}</td>
                  <td>{x.visits}</td>
                  <td>{x.votes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function FlagsView() {
  const f = useLoad(adminApi.flags, []);
  if (!f.data) return <Loading error={f.error} />;
  if (f.data.length === 0) return <div className="card">通報はまだありません。</div>;
  const act = async (t: (typeof f.data)[number], action: "hide" | "show" | "delete") => {
    await adminApi.moderate(t.target_type, t.target_id, action).catch((e) => alert(e.message));
    f.reload();
  };
  return (
    <div className="card table-scroll">
      <table className="table">
        <thead>
          <tr>
            <th>種類</th>
            <th>内容</th>
            <th>通報</th>
            <th>状態</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {f.data.map((t) => (
            <tr key={`${t.target_type}-${t.target_id}`}>
              <td>{TYPE_LABEL[t.target_type]}</td>
              <td>{t.text}</td>
              <td>{t.count}</td>
              <td>{t.hidden ? "非表示" : "表示中"}</td>
              <td className="row wrap-gap">
                {t.hidden ? (
                  <button className="btn small ghost" onClick={() => act(t, "show")}>
                    表示に戻す
                  </button>
                ) : (
                  <button className="btn small ghost" onClick={() => act(t, "hide")}>
                    非表示にする
                  </button>
                )}
                {(t.target_type === "story" || t.target_type === "reason") && (
                  <button className="btn small danger" onClick={() => confirm("削除しますか？元に戻せません。") && act(t, "delete")}>
                    削除
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AxisRow({ s, onSaved }: { s: AdminStatement; onSaved: () => void }) {
  const meta = useMeta();
  const [axis, setAxis] = useState(s.axis_key ?? "");
  const [dir, setDir] = useState(s.direction ? String(s.direction) : "");
  const ax = meta?.axes.find((a) => a.key === axis);
  const dirty = axis !== (s.axis_key ?? "") || dir !== (s.direction ? String(s.direction) : "");
  return (
    <tr className={s.hidden ? "muted" : ""}>
      <td className="small">{s.topic_title}</td>
      <td>
        {s.body}
        {s.origin === "user" && <span className="chip muted">参加者</span>}
      </td>
      <td>
        <select value={axis} onChange={(e) => (setAxis(e.target.value), setDir(""))}>
          <option value="">なし</option>
          {meta?.axes.map((a) => (
            <option key={a.key} value={a.key}>
              {a.name}
            </option>
          ))}
        </select>
        {ax && (
          <select value={dir} onChange={(e) => setDir(e.target.value)}>
            <option value="">賛成すると…</option>
            <option value="-1">{ax.left}</option>
            <option value="1">{ax.right}</option>
          </select>
        )}
      </td>
      <td>
        <button
          className="btn small"
          disabled={!dirty || (Boolean(axis) && !dir)}
          onClick={async () => {
            await adminApi.tag(s.id, axis || null, axis ? Number(dir) : null).catch((e) => alert(e.message));
            onSaved();
          }}
        >
          保存
        </button>
      </td>
    </tr>
  );
}

function AxesView() {
  const s = useLoad(adminApi.statements, []);
  const [onlyUntagged, setOnlyUntagged] = useState(true);
  if (!s.data) return <Loading error={s.error} />;
  const rows = s.data.filter((x) => !onlyUntagged || !x.axis_key);
  return (
    <div className="card">
      <label className="row small">
        <input type="checkbox" checked={onlyUntagged} onChange={(e) => setOnlyUntagged(e.target.checked)} /> 軸が付いていない論点だけ表示
      </label>
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>議題</th>
              <th>論点</th>
              <th>価値観の軸・賛成したときの向き</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((x) => (
              <AxisRow key={`${x.id}-${x.axis_key}-${x.direction}`} s={x} onSaved={s.reload} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Admin() {
  const [key, setKey] = useState(adminKey.get() ?? "");
  const [authed, setAuthed] = useState(Boolean(adminKey.get()));
  const [tab, setTab] = useState<"metrics" | "flags" | "axes">("metrics");

  if (!authed) {
    return (
      <div className="card narrow">
        <h1>管理画面</h1>
        <label className="field">
          <span>合言葉</span>
          <input type="password" value={key} onChange={(e) => setKey(e.target.value)} />
        </label>
        <button
          className="btn primary"
          disabled={!key}
          onClick={() => {
            adminKey.set(key);
            setAuthed(true);
          }}
        >
          開く
        </button>
      </div>
    );
  }
  return (
    <>
      <div className="row between">
        <h1>管理画面</h1>
        <button
          className="link small"
          onClick={() => {
            adminKey.set(null);
            setAuthed(false);
          }}
        >
          合言葉を入れ直す
        </button>
      </div>
      <div className="tabs" role="tablist">
        {(
          [
            ["metrics", "計測"],
            ["flags", "通報"],
            ["axes", "軸の紐づけ"],
          ] as const
        ).map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
            {label}
          </button>
        ))}
      </div>
      {tab === "metrics" && <MetricsView />}
      {tab === "flags" && <FlagsView />}
      {tab === "axes" && <AxesView />}
    </>
  );
}
