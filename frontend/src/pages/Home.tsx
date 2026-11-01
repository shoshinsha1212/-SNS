import { Link } from "react-router-dom";
import { api, type TopicSummary } from "../api";
import { Loading, useLoad } from "../common";

function TopicCard({ t }: { t: TopicSummary }) {
  const started = t.my_answered > 0;
  const to = t.completed ? `/t/${t.id}/results` : `/t/${t.id}`;
  return (
    <Link to={to} className="card topic-card">
      <div className="topic-card-head">
        <h3>{t.title}</h3>
        {t.origin === "user" && <span className="chip muted">参加者の議題</span>}
      </div>
      {t.description && <p className="muted">{t.description}</p>}
      <div className="topic-card-foot">
        <span className="muted small">
          {t.n_statements}問 ・ {t.n_participants}人が回答
        </span>
        <span className={`btn small ${t.completed ? "ghost" : "primary"}`}>
          {t.completed ? "結果を見る" : started ? `続きから（${t.my_answered}/${t.n_statements}）` : "答える"}
        </span>
      </div>
      {started && !t.completed && (
        <div className="progress" aria-hidden>
          <span style={{ width: `${(t.my_answered / Math.max(1, t.n_statements)) * 100}%` }} />
        </div>
      )}
    </Link>
  );
}

export default function Home() {
  const topics = useLoad(api.topics, []);
  const me = useLoad(api.me, []);

  if (!topics.data) return <Loading error={topics.error} />;
  const done = me.data?.completed_topics ?? topics.data.filter((t) => t.completed).length;
  const required = me.data?.map_required ?? 3;
  const left = Math.max(0, required - done);

  return (
    <>
      <section className="hero">
        <h1>社会の議題に答えて、自分の位置と価値観を知る</h1>
        <p>
          1つの議題は8問ほど、3分で答えられます。答えると、あなたが多数派か少数派か、反対側の人がなぜそう考えるのかが分かります。
          {required}つの議題に答えると、あなたの価値観マップが完成します。
        </p>
      </section>

      <Link to="/map" className="card map-progress">
        <div>
          <strong>価値観マップ</strong>
          <p className="muted small">
            {left === 0 ? "完成しました。マップを見る →" : done === 0 ? `${required}議題に答えると完成します` : `あと${left}議題で完成（途中経過を見る →）`}
          </p>
        </div>
        <div className="dots" aria-label={`${done} / ${required} 議題完了`}>
          {Array.from({ length: required }, (_, i) => (
            <span key={i} className={i < done ? "on" : ""} />
          ))}
        </div>
      </Link>

      <div className="section-head">
        <h2>議題</h2>
        <Link to="/new" className="btn ghost small">
          ＋ 議題を作る
        </Link>
      </div>
      <div className="topic-list">
        {topics.data.map((t) => (
          <TopicCard key={t.id} t={t} />
        ))}
      </div>
    </>
  );
}
