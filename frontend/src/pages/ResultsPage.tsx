import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { api, track, type StatementResult, type StoryItem, type TopicSummary } from "../api";
import { Collapse, FlagButton, Loading, PrivacyNote, VoteChip, pct, useLoad, useMeta } from "../common";

const LABEL: Record<StatementResult["label"], string | null> = {
  consensus_agree: "みんな賛成で一致",
  consensus_disagree: "みんな反対で一致",
  divided: "意見が割れている",
  leaning: null,
  few: null,
};

// Polis のレポートにならい、合意点と割れた論点を分けて見せる
const SECTIONS: { key: string; title: string; description: string; labels: StatementResult["label"][] }[] = [
  {
    key: "consensus",
    title: "みんなの合意点",
    description: "賛成・反対を選んだ人の7割以上が同じ答えだった論点です。",
    labels: ["consensus_agree", "consensus_disagree"],
  },
  {
    key: "divided",
    title: "意見が割れた論点",
    description: "賛成と反対がほぼ半々（4〜6割）に分かれた論点です。",
    labels: ["divided"],
  },
  {
    key: "other",
    title: "そのほかの論点",
    description: "どちらかに傾いているものと、まだ回答が少ないものです。",
    labels: ["leaning", "few"],
  },
];

/** Polis と同じく、賛成・反対・わからないの3色で、答えた人全体に対する割合を見せる。 */
function Bar({ agree, disagree, pass, compact }: { agree: number; disagree: number; pass: number; compact?: boolean }) {
  const total = agree + disagree + pass;
  if (total === 0) return <p className="small muted">まだ回答がありません</p>;
  const w = (n: number) => `${(n / total) * 100}%`;
  return (
    <div className={`bar-wrap ${compact ? "compact" : ""}`}>
      <div
        className="bar"
        role="img"
        aria-label={`賛成${agree}人、反対${disagree}人、わからない${pass}人`}
      >
        <span className="agree" style={{ width: w(agree) }} />
        <span className="disagree" style={{ width: w(disagree) }} />
        <span className="pass" style={{ width: w(pass) }} />
      </div>
      {!compact && (
        <div className="legend small">
          <span className="agree-text">賛成 {pct(agree / total)}</span>
          <span className="disagree-text">反対 {pct(disagree / total)}</span>
          <span className="muted">わからない {pct(pass / total)}</span>
          <span className="muted">（{total}人）</span>
        </div>
      )}
    </div>
  );
}

function Groups({ s }: { s: StatementResult }) {
  const shown = s.groups.filter((g) => g.agree + g.disagree + g.pass > 0);
  if (shown.length < 2) return null;
  return (
    <div className="groups">
      {shown.map((g) => (
        <div key={g.key} className="group-row">
          <span className="small">{g.label}</span>
          <Bar agree={g.agree} disagree={g.disagree} pass={g.pass} compact />
          <span className="small muted">
            賛成 {pct(g.agree + g.disagree ? g.agree / (g.agree + g.disagree) : null)}・{g.agree + g.disagree + g.pass}人
          </span>
        </div>
      ))}
    </div>
  );
}

function StoryList({ items, title }: { items: StoryItem[]; title: string }) {
  const [hidden, setHidden] = useState<number[]>([]);
  const shown = items.filter((i) => !hidden.includes(i.id));
  if (shown.length === 0) return null;
  return (
    <div className="stories">
      <p className="small strong">{title}</p>
      {shown.map((st) => (
        <blockquote key={st.id} className="story">
          <p>{st.body}</p>
          {st.mine ? <span className="small muted">あなたの体験談</span> : <FlagButton type="story" id={st.id} onHidden={() => setHidden([...hidden, st.id])} />}
        </blockquote>
      ))}
    </div>
  );
}

function StoryForm({ statementId, onPosted }: { statementId: number; onPosted: () => void }) {
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="story-form">
      <textarea
        rows={3}
        maxLength={400}
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="この考えに至った、あなた自身の体験を書いてください（10〜400字）"
      />
      <PrivacyNote />
      {error && <p className="error-text">{error}</p>}
      <button
        className="btn small"
        disabled={busy || body.trim().length < 10}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            await api.postStory(statementId, body);
            setBody("");
            onPosted();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        体験談を投稿する
      </button>
    </div>
  );
}

function StatementBlock({ s, topicId, minN, onChanged }: { s: StatementResult; topicId: number; minN: number; onChanged: () => void }) {
  const [hiddenReasons, setHiddenReasons] = useState<number[]>([]);
  const label = LABEL[s.label];
  const opposite = s.my_vote === 1 ? "disagree" : s.my_vote === -1 ? "agree" : null;
  const reasonSides = opposite ? [opposite] : (["agree", "disagree"] as const);
  const sideName = (side: string) => (side === "agree" ? "賛成" : "反対");
  const reasons = reasonSides.flatMap((side) => s.reasons[side as "agree" | "disagree"].map((r) => ({ ...r, side })));
  const shownReasons = reasons.filter((r) => !hiddenReasons.includes(r.id));
  const stories = opposite
    ? { first: s.stories[opposite], firstTitle: `${sideName(opposite)}した人の体験談`, rest: [...s.stories[opposite === "agree" ? "disagree" : "agree"], ...s.stories.other] }
    : { first: [...s.stories.agree, ...s.stories.disagree], firstTitle: "賛成・反対した人の体験談", rest: s.stories.other };

  return (
    <article className="card result-card">
      <div className="row between wrap-gap">
        <VoteChip value={s.my_vote} />
        {label && <span className={`chip ${s.label}`}>{label}</span>}
      </div>
      <p className="statement-body small-body">{s.body}</p>
      <Bar agree={s.agree} disagree={s.disagree} pass={s.pass} />
      {s.n > 0 && s.n < minN && <p className="small muted">賛成・反対の回答が{minN}人未満のため、割合は参考値です。</p>}
      {s.same_rate != null && s.n >= minN && (
        <p className="small">
          賛成・反対を選んだ人のうち、あなたと同じ意見は <strong>{pct(s.same_rate)}</strong>
          {s.same_rate < 0.5 ? "（少数派）" : "（多数派）"}
        </p>
      )}
      <Groups s={s} />

      {shownReasons.length > 0 && (
        <div className="reasons">
          <p className="small strong">{opposite ? `${sideName(opposite)}した人の理由` : "理由"}</p>
          <ul>
            {shownReasons.map((r) => (
              <li key={r.id}>
                <span className={`dot ${r.side}`} aria-hidden />
                {r.text}
                <FlagButton type="reason" id={r.id} onHidden={() => setHiddenReasons([...hiddenReasons, r.id])} />
              </li>
            ))}
          </ul>
        </div>
      )}

      <Collapse
        label={s.n_stories > 0 ? `体験談（${s.n_stories}件）を読む・書く` : "体験談を書く"}
        onOpen={() => s.n_stories > 0 && track("story_read", topicId, s.id)}
      >
        <StoryList items={stories.first} title={stories.firstTitle} />
        <StoryList items={stories.rest} title={opposite ? "あなたと同じ側・その他の体験談" : "その他の体験談"} />
        <StoryForm statementId={s.id} onPosted={onChanged} />
      </Collapse>
      <div className="row end">
        <FlagButton type="statement" id={s.id} onHidden={onChanged} label="この論点を通報" />
      </div>
    </article>
  );
}

function Understanding({ topicId, initial }: { topicId: number; initial: number | null }) {
  const [score, setScore] = useState<number | null>(initial);
  return (
    <div className="card">
      <h3>最後にひとつだけ</h3>
      <p>この議題で、反対側の考えが前より理解できましたか？</p>
      <div className="scale" role="radiogroup" aria-label="理解度">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            role="radio"
            aria-checked={score === n}
            className={`btn ${score === n ? "primary" : "ghost"}`}
            onClick={async () => {
              setScore(n);
              await api.understanding(topicId, n).catch(() => undefined);
            }}
          >
            {n}
          </button>
        ))}
      </div>
      <div className="row between small muted">
        <span>1 まったく</span>
        <span>5 とても</span>
      </div>
      {score != null && <p className="small">回答ありがとうございました。</p>}
    </div>
  );
}

export default function ResultsPage() {
  const id = Number(useParams().id);
  const loc = useLocation();
  const flash = (loc.state ?? {}) as { completedNow?: boolean; completedTopics?: number; mapCompletedNow?: boolean };
  const res = useLoad(() => api.results(id), [id]);
  const topics = useLoad(api.topics, [id]);
  const meta = useMeta();

  useEffect(() => {
    track("result_view", id);
    window.scrollTo(0, 0);
  }, [id]);

  if (!res.data) return <Loading error={res.error} />;
  const r = res.data;
  const sum = r.summary;
  const next: TopicSummary | undefined = topics.data?.find((t) => !t.completed && t.id !== id);
  const done = flash.completedTopics ?? topics.data?.filter((t) => t.completed).length ?? 0;
  const required = meta?.map_required ?? 3;

  return (
    <>
      <Link to="/" className="link small">
        ← 議題一覧
      </Link>
      <h1>{r.topic.title}：みんなの結果</h1>

      {flash.completedNow && (
        <div className={`card celebrate ${flash.mapCompletedNow ? "complete" : ""}`}>
          {flash.mapCompletedNow ? (
            <>
              <strong>価値観マップが完成しました！</strong>
              <p>{required}つの議題への答えから、あなたの価値観の位置が分かりました。</p>
              <Link to="/map" className="btn primary">
                価値観マップを見る
              </Link>
            </>
          ) : (
            <>
              <strong>この議題に答え終えました（{done} / {required}）</strong>
              <p>
                価値観マップの途中経過が見られます。あと{Math.max(0, required - done)}議題で完成します。
              </p>
              <div className="row">
                <Link to="/map" className="btn ghost">
                  途中経過を見る
                </Link>
                {next && (
                  <Link to={`/t/${next.id}`} className="btn primary">
                    次の議題「{next.title}」に答える
                  </Link>
                )}
              </div>
            </>
          )}
        </div>
      )}

      <div className="card summary">
        <p className="small muted">{r.n_participants}人が回答</p>
        {sum.n_answered === 0 ? (
          <p>
            まだ答えていません。<Link to={`/t/${id}`}>答える →</Link>
          </p>
        ) : sum.n_rated === 0 ? (
          <p>回答がまだ少ないため、あなたが多数派か少数派かはもう少し人が集まってから表示されます。</p>
        ) : (
          <>
            <p className="big">
              あなたは<strong>{sum.n_rated}問中{sum.n_majority}問</strong>で多数派でした。
            </p>
            {sum.most_minority && (
              <p>
                いちばん少数派だったのは「{sum.most_minority.body}」（同じ意見は{pct(sum.most_minority.same_rate)}）。
              </p>
            )}
          </>
        )}
      </div>

      {SECTIONS.map((sec) => {
        const items = r.statements.filter((s) => sec.labels.includes(s.label));
        if (items.length === 0) return null;
        return (
          <section key={sec.key} className="result-section">
            <h2>
              {sec.title} <span className="count">{items.length}</span>
            </h2>
            <p className="small muted">{sec.description}</p>
            {items.map((s) => (
              <StatementBlock key={s.id} s={s} topicId={id} minN={r.min_n} onChanged={res.reload} />
            ))}
          </section>
        );
      })}

      {sum.n_answered > 0 && <Understanding topicId={id} initial={r.my_understanding} />}

      <div className="row center">
        {next && (
          <Link to={`/t/${next.id}`} className="btn primary">
            次の議題に答える
          </Link>
        )}
        <Link to="/map" className="btn ghost">
          価値観マップを見る
        </Link>
      </div>
    </>
  );
}
