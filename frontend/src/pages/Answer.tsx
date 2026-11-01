import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, track, type TopicDetail } from "../api";
import { Collapse, Loading, PrivacyNote, useLoad, useMeta } from "../common";

/** 最初の回答の前に1回だけ聞く任意の属性。 */
function ProfilePrompt({ onDone }: { onDone: () => void }) {
  const meta = useMeta();
  const [age, setAge] = useState<string>("");
  const [student, setStudent] = useState<"" | "yes" | "no">("");
  const [busy, setBusy] = useState(false);

  const save = async (skip: boolean) => {
    setBusy(true);
    try {
      if (skip) {
        await api.saveProfile(null, null);
        track("profile_skip");
      } else {
        await api.saveProfile(age || null, student === "" ? null : student === "yes");
      }
    } finally {
      onDone();
    }
  };

  return (
    <div className="card">
      <h2>はじめに（任意）</h2>
      <p className="muted">
        答えると、結果で「大学生の中ではどうか」も比べられます。答えなくても参加できます。あとから変えることはできません。
      </p>
      <label className="field">
        <span>年齢層</span>
        <select value={age} onChange={(e) => setAge(e.target.value)}>
          <option value="">答えない</option>
          {meta?.age_bands.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>
      </label>
      <fieldset className="field">
        <legend>大学生（大学院生・短大生を含む）ですか</legend>
        <div className="seg">
          {(
            [
              ["yes", "はい"],
              ["no", "いいえ"],
              ["", "答えない"],
            ] as const
          ).map(([v, label]) => (
            <label key={v} className={student === v ? "on" : ""}>
              <input type="radio" name="student" checked={student === v} onChange={() => setStudent(v)} />
              {label}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="row">
        <button className="btn primary" disabled={busy} onClick={() => save(false)}>
          この内容で始める
        </button>
        <button className="btn ghost" disabled={busy} onClick={() => save(true)}>
          答えずに始める
        </button>
      </div>
    </div>
  );
}

function AddStatement({ topic, onAdded }: { topic: TopicDetail; onAdded: () => void }) {
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Collapse label="この議題に論点を追加する">
      <p className="muted small">賛成・反対で答えられる一文にしてください（5〜100字）。追加した論点は、ほかの人の質問にも出ます。</p>
      <textarea value={body} maxLength={100} rows={2} onChange={(e) => setBody(e.target.value)} placeholder="例：〇〇は△△すべきだ" />
      <PrivacyNote />
      {error && <p className="error-text">{error}</p>}
      <button
        className="btn small"
        disabled={busy || body.trim().length < 5}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            await api.addStatement(topic.id, { body });
            setBody("");
            onAdded();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        追加する
      </button>
    </Collapse>
  );
}

export default function Answer() {
  const id = Number(useParams().id);
  const nav = useNavigate();
  const topic = useLoad(() => api.topic(id), [id]);
  const me = useLoad(api.me, []);
  const [index, setIndex] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [showReason, setShowReason] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [profileDone, setProfileDone] = useState(false);

  useEffect(() => {
    track("topic_view", id);
  }, [id]);

  const stmts = topic.data?.statements ?? [];
  const votes = topic.data?.my_votes ?? {};
  const firstUnanswered = useMemo(() => stmts.findIndex((s) => !(String(s.id) in votes)), [stmts, votes]);

  // 読み込み直後は最初の未回答の論点から
  useEffect(() => {
    if (topic.data && index === null) setIndex(firstUnanswered === -1 ? 0 : firstUnanswered);
  }, [topic.data, index, firstUnanswered]);

  const current = index !== null ? stmts[index] : undefined;
  useEffect(() => {
    const prev = current ? votes[String(current.id)] : undefined;
    setReason(prev?.reason ?? "");
    setShowReason(Boolean(prev?.reason));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.id]);

  if (!topic.data || !me.data || index === null) return <Loading error={topic.error ?? me.error} />;
  const t = topic.data;
  if (!me.data.profile_asked && !profileDone && Object.keys(votes).length === 0) {
    return <ProfilePrompt onDone={() => setProfileDone(true)} />;
  }
  if (!current) return <div className="card">この議題にはまだ論点がありません。</div>;

  const answeredCount = Object.keys(votes).length;
  const myPrev = votes[String(current.id)]?.value;

  const vote = async (value: number) => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.vote(current.id, value, value !== 0 && reason.trim() ? reason : null);
      const nextVotes = { ...votes, [String(current.id)]: { value, reason: value !== 0 ? reason.trim() || null : null } };
      topic.setData({ ...t, my_votes: nextVotes });
      const next = stmts.findIndex((s, i) => i > index && !(String(s.id) in nextVotes));
      const anyLeft = stmts.findIndex((s) => !(String(s.id) in nextVotes));
      if (next !== -1) setIndex(next);
      else if (anyLeft !== -1) setIndex(anyLeft);
      else
        nav(`/t/${t.id}/results`, {
          state: { completedNow: r.topic_completed_now, completedTopics: r.completed_topics, mapCompletedNow: r.map_completed_now },
        });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="answer-head">
        <Link to="/" className="link small">
          ← 議題一覧
        </Link>
        <h1>{t.title}</h1>
        {t.description && <p className="muted">{t.description}</p>}
        <div className="progress-row">
          <div className="progress" aria-hidden>
            <span style={{ width: `${(answeredCount / stmts.length) * 100}%` }} />
          </div>
          <span className="small muted">
            {answeredCount} / {stmts.length}
          </span>
        </div>
      </div>

      <div className="card statement-card">
        <p className="small muted">
          {index + 1}問目{current.origin === "user" && "（参加者が追加した論点）"}
        </p>
        <p className="statement-body">{current.body}</p>
        <div className="vote-buttons">
          <button className={`btn vote agree ${myPrev === 1 ? "on" : ""}`} disabled={busy} onClick={() => vote(1)}>
            賛成
          </button>
          <button className={`btn vote disagree ${myPrev === -1 ? "on" : ""}`} disabled={busy} onClick={() => vote(-1)}>
            反対
          </button>
          <button className={`btn vote pass ${myPrev === 0 ? "on" : ""}`} disabled={busy} onClick={() => vote(0)}>
            わからない
          </button>
        </div>
        {showReason ? (
          <div className="reason">
            <label className="small" htmlFor="reason">
              理由をひとこと（任意・80字まで）：反対側の人に表示されます
            </label>
            <input id="reason" value={reason} maxLength={80} onChange={(e) => setReason(e.target.value)} placeholder="例：自分の家庭の事情から" />
            <PrivacyNote />
          </div>
        ) : (
          <button type="button" className="link small" onClick={() => setShowReason(true)}>
            ＋ 理由をひとこと添える（任意）
          </button>
        )}
        {error && <p className="error-text">{error}</p>}
        <div className="row between small">
          <button type="button" className="link" disabled={index === 0} onClick={() => setIndex(index - 1)}>
            ← 前の問い
          </button>
          {answeredCount > 0 && (
            <Link to={`/t/${t.id}/results`} className="link">
              途中の結果を見る
            </Link>
          )}
          <button type="button" className="link" disabled={index >= stmts.length - 1} onClick={() => setIndex(index + 1)}>
            次の問い →
          </button>
        </div>
      </div>

      <AddStatement topic={t} onAdded={topic.reload} />
    </>
  );
}
