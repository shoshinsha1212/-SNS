import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, track, type MapAxis } from "../api";
import { Collapse, Loading, VOTE_LABEL, useLoad } from "../common";

function AxisRow({ a }: { a: MapAxis }) {
  const max = Math.max(1, ...a.histogram);
  const total = a.histogram.reduce((x, y) => x + y, 0);
  const pos = a.score == null ? null : ((a.score + 1) / 2) * 100;
  return (
    <div className="card axis">
      <div className="row between">
        <h3>{a.name}</h3>
        {a.score == null && <span className="chip muted">まだ回答がありません</span>}
      </div>
      <p className="small muted">{a.description}</p>
      <div className="axis-scale">
        <div className="hist" aria-label={`全体の分布（${total}人）`}>
          {a.histogram.map((n, i) => (
            <span key={i} className={i === a.my_bin ? "mine" : ""} style={{ height: `${(n / max) * 100}%` }} title={`${n}人`} />
          ))}
        </div>
        <div className="track">{pos != null && <span className="me" style={{ left: `${pos}%` }} aria-label="あなたの位置" />}</div>
        <div className="row between small">
          <span>← {a.left}</span>
          <span>{a.right} →</span>
        </div>
      </div>
      <p className="small muted">棒グラフは回答した人全体（{total}人）の分布。色の濃い棒があなたのいる区間です。</p>
      {a.basis.length > 0 && (
        <Collapse label={`根拠になった回答（${a.basis.length}問）`}>
          <ul className="basis">
            {a.basis.map((b) => (
              <li key={b.statement_id}>
                「{b.body}」に{VOTE_LABEL[b.my_vote]} → <strong>{b.toward}</strong>寄り
                <span className="small muted">（{b.topic_title}）</span>
              </li>
            ))}
          </ul>
        </Collapse>
      )}
    </div>
  );
}

export default function MapPage() {
  const m = useLoad(api.map, []);
  const [shared, setShared] = useState<string | null>(null);
  useEffect(() => track("map_view"), []);

  if (!m.data) return <Loading error={m.error} />;
  const d = m.data;
  const left = Math.max(0, d.required - d.completed_topics);

  if (d.completed_topics === 0 && !d.axes.some((a) => a.score != null)) {
    return (
      <div className="card center-text">
        <h1>価値観マップ</h1>
        <p>{d.required}つの議題に答えると、あなたの価値観マップが完成します。1つ答え終えた時点で、途中経過も見られます。</p>
        <Link to="/" className="btn primary">
          議題に答える
        </Link>
      </div>
    );
  }

  const share = async () => {
    const text = `私の価値観は「${d.type_name ?? "まだ分析中"}」でした。社会の議題に答えて、自分の位置を知ろう。`;
    const url = window.location.origin;
    track("share");
    try {
      if (navigator.share) {
        await navigator.share({ title: "成果型SNS 価値観マップ", text, url });
        setShared("共有しました");
      } else {
        await navigator.clipboard.writeText(`${text} ${url}`);
        setShared("共有用の文章をコピーしました");
      }
    } catch {
      setShared(null);
    }
  };

  return (
    <>
      <div className={`card map-hero ${d.complete ? "complete" : ""}`}>
        <p className="small muted">{d.complete ? "あなたの価値観マップ" : `途中経過（${d.completed_topics} / ${d.required}議題）`}</p>
        <h1>{d.type_name ?? "分析中"}</h1>
        {d.code && <p className="code" aria-label="4つの軸の傾き">{d.code.split("").join(" ")}</p>}
        {!d.complete && <p>あと{left}議題に答えると完成します。今の結果は仮のものです。</p>}
        <div className="row center">
          {!d.complete && (
            <Link to="/" className="btn primary">
              次の議題に答える
            </Link>
          )}
          <button className="btn ghost" onClick={share}>
            結果を共有する
          </button>
        </div>
        {shared && <p className="small">{shared}</p>}
      </div>
      {d.axes.map((a) => (
        <AxisRow key={a.key} a={a} />
      ))}
      <p className="small muted">
        タイプ名は、4つの軸のうち傾きが大きい2つから付けています。価値観の軸と論点の対応は運営が作った仮のもので、今後見直します。
      </p>
    </>
  );
}
