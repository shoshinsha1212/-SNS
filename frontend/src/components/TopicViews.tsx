import { useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  api,
  type ConvertResponse,
  type PostStatementResponse,
  type Section,
  type StoryKind,
  type TopicDetail,
  type VoteResponse,
  type VoteValue,
  type StatementListItem,
} from "../api";
import { useAction, useAsync } from "../hooks";
import {
  formatDate,
  gapPoints,
  gapWords,
  ORIGIN_LABEL,
  pct,
  SECTION_DESC,
  SECTION_LABEL,
  SECTION_ORDER,
} from "../labels";
import { PositionRateBars, StoryCardView } from "./Common";

export function PositionSelector({
  topic,
  onSaved,
}: {
  topic: TopicDetail;
  onSaved: (updated: TopicDetail) => void;
}) {
  const [selected, setSelected] = useState<Record<string, number>>(() => ({
    ...topic.my_positions,
  }));
  const { busy, error, exec } = useAction();

  const pickOption = (axisId: number, optId: number) => {
    const next = { ...selected, [String(axisId)]: optId };
    setSelected(next);
    exec(async () => {
      const updated = await api.putPositions(topic.id, next);
      onSaved(updated);
    });
  };

  return (
    <div className="card" style={{ borderLeft: "4px solid var(--brand-blue)", background: "#ffffff" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "0.5rem", marginBottom: "0.85rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span style={{ fontSize: "1.05rem", fontWeight: 800, color: "var(--text-main)" }}>
              あなたの立場を選択してください（ワンタップ）
            </span>
            {busy && <span className="badge">保存中…</span>}
          </div>
          <div style={{ fontSize: "0.86rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
            人の意見は置かれた立場によって決まる側面があります。あなたの立場を選ぶことで、立場ごとの見え方の違い（ギャップ）や共通合意が可視化されます。
          </div>
        </div>
      </div>

      {error && <div className="error-box">{error}</div>}

      <div style={{ display: "grid", gap: "0.85rem" }}>
        {topic.axes.map((ax) => (
          <div key={ax.id}>
            <div style={{ fontSize: "0.88rem", fontWeight: 800, color: "var(--text-main)", marginBottom: "0.45rem" }}>
              {ax.name}
            </div>
            <div className="position-chip-group">
              {ax.options.map((opt) => {
                const isChosen = selected[String(ax.id)] === opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    className={`position-chip ${isChosen ? "active" : ""}`}
                    disabled={busy}
                    onClick={() => pickOption(ax.id, opt.id)}
                  >
                    {isChosen ? `✓ ${opt.label}` : opt.label}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function VoteTab({
  topicId,
  onOpenStatement,
  onVoted,
}: {
  topicId: number;
  onOpenStatement: (sid: number) => void;
  onVoted: () => void;
}) {
  const { data: stmts, reload: reloadList } = useAsync(() => api.listStatements(topicId), [topicId]);
  const [currentIndex, setCurrentIndex] = useState<number>(0);
  const [lastResult, setLastResult] = useState<{
    statementId: number;
    text: string;
    n_stories: number;
    vote: VoteResponse;
  } | null>(null);
  const { busy, error: voteError, exec } = useAction();

  const total = stmts?.length ?? 0;
  const votedCount = stmts?.filter((s) => s.my_vote !== null).length ?? 0;
  const progressPct = total > 0 ? Math.round((votedCount / total) * 100) : 0;

  // Active statement
  const activeStatement: StatementListItem | null =
    stmts && stmts.length > 0 ? stmts[Math.min(currentIndex, stmts.length - 1)] : null;

  const castVote = (sid: number, text: string, n_stories: number, val: VoteValue) =>
    exec(async () => {
      const res = await api.vote(sid, val);
      setLastResult({ statementId: sid, text, n_stories, vote: res });
      onVoted();
      reloadList();

      // Automatically advance to the next unvoted statement if available
      if (stmts) {
        const nextUnvoted = stmts.findIndex((s, idx) => idx > currentIndex && s.my_vote === null);
        if (nextUnvoted !== -1) {
          setCurrentIndex(nextUnvoted);
        } else if (currentIndex < stmts.length - 1) {
          setCurrentIndex(currentIndex + 1);
        }
      }
    });

  return (
    <div className="voting-container">
      {/* Progress Header */}
      <div style={{ marginBottom: "1.1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "0.85rem", fontWeight: 800, color: "var(--text-muted)", marginBottom: "0.45rem" }}>
          <span>投票の進捗</span>
          <span>
            {votedCount} / {total} 問完了（{progressPct}%）
          </span>
        </div>
        <div className="progress-track" style={{ height: "10px" }}>
          <div
            className="progress-agree"
            style={{
              width: `${progressPct}%`,
              background: "linear-gradient(90deg, #06b6d4, #2563eb, #8b5cf6)",
              transition: "width 0.3s ease",
            }}
          />
        </div>
      </div>

      {voteError && <div className="error-box">{voteError}</div>}

      {/* Polis Card Voter */}
      {activeStatement ? (
        <div className="vote-card">
          <div className="vote-card-header">
            <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", alignItems: "center" }}>
              <span className="badge" style={{ background: "var(--bg-app)", fontWeight: 800 }}>
                質問 {currentIndex + 1} / {total}
              </span>
              {ORIGIN_LABEL[activeStatement.origin] && (
                <span className="badge">{ORIGIN_LABEL[activeStatement.origin]}</span>
              )}
            </div>

            <button
              type="button"
              className="btn btn-sm"
              style={{ color: "var(--brand-blue)", borderRadius: "var(--radius-pill)" }}
              onClick={() => onOpenStatement(activeStatement.id)}
            >
              📖 原体験 {activeStatement.n_stories}件
            </button>
          </div>

          <div className="vote-statement-text">
            {activeStatement.text}
          </div>

          {activeStatement.my_vote !== null && (
            <div style={{ marginBottom: "0.85rem" }}>
              <span className="badge" style={{
                background: activeStatement.my_vote === 1 ? "var(--agree-bg)" : activeStatement.my_vote === -1 ? "var(--disagree-bg)" : "var(--pass-bg)",
                color: activeStatement.my_vote === 1 ? "var(--agree-text)" : activeStatement.my_vote === -1 ? "var(--disagree-text)" : "var(--pass-text)",
                borderColor: activeStatement.my_vote === 1 ? "var(--agree-border)" : activeStatement.my_vote === -1 ? "var(--disagree-border)" : "var(--pass-border)",
                fontWeight: 800,
                fontSize: "0.84rem"
              }}>
                ✓ 投票済み：{activeStatement.my_vote === 1 ? "賛成" : activeStatement.my_vote === -1 ? "反対" : "パス"} （ボタンで変更できます）
              </span>
            </div>
          )}

          {/* 3 Main Action Buttons */}
          <div className="vote-actions-grid">
            <button
              type="button"
              className="btn-vote btn-vote-agree"
              disabled={busy}
              onClick={() => castVote(activeStatement.id, activeStatement.text, activeStatement.n_stories, 1)}
            >
              <span className="btn-vote-icon">👍</span>
              <span>賛成 (Agree)</span>
            </button>

            <button
              type="button"
              className="btn-vote btn-vote-disagree"
              disabled={busy}
              onClick={() => castVote(activeStatement.id, activeStatement.text, activeStatement.n_stories, -1)}
            >
              <span className="btn-vote-icon">👎</span>
              <span>反対 (Disagree)</span>
            </button>

            <button
              type="button"
              className="btn-vote btn-vote-pass"
              disabled={busy}
              onClick={() => castVote(activeStatement.id, activeStatement.text, activeStatement.n_stories, 0)}
            >
              <span className="btn-vote-icon">➡️</span>
              <span>パス (Pass)</span>
            </button>
          </div>

          {/* Quick Prev / Next Controls */}
          <div className="vote-nav-controls">
            <button
              type="button"
              className="btn btn-sm"
              disabled={currentIndex === 0}
              onClick={() => setCurrentIndex((idx) => Math.max(0, idx - 1))}
            >
              ← 前の質問
            </button>

            <span style={{ fontSize: "0.82rem", color: "var(--text-muted)", fontWeight: 700 }}>
              #{activeStatement.id}
            </span>

            <button
              type="button"
              className="btn btn-sm"
              disabled={currentIndex >= total - 1}
              onClick={() => setCurrentIndex((idx) => Math.min(total - 1, idx + 1))}
            >
              次の質問 →
            </button>
          </div>
        </div>
      ) : (
        <div className="vote-card" style={{ padding: "3rem 1.5rem" }}>
          <div style={{ fontSize: "2.8rem", marginBottom: "0.5rem" }}>🎉</div>
          <h2 style={{ fontSize: "1.35rem", fontWeight: 800, margin: "0.5rem 0" }}>
            すべての原則への投票が完了しました！
          </h2>
          <p style={{ color: "var(--text-muted)", fontSize: "0.95rem", maxWidth: 460, margin: "0 auto 1rem", lineHeight: 1.6 }}>
            ご協力ありがとうございます。あなたの投票は記録され、最新の1票として統計と意見マップに反映されています。
          </p>
          <div style={{ background: "rgba(37,99,235,0.06)", border: "1px solid rgba(37,99,235,0.2)", borderRadius: "var(--radius-md)", padding: "0.75rem 1rem", maxWidth: 480, margin: "0 auto 1.5rem", fontSize: "0.85rem", color: "var(--brand-blue)" }}>
            ℹ️ あなたの投票は重複せず、回答を変更した場合は最新の内容に上書き更新されます。
          </div>
          <div style={{ display: "flex", justifyContent: "center", gap: "0.75rem", flexWrap: "wrap" }}>
            <button
              type="button"
              className="btn"
              onClick={() => setCurrentIndex(0)}
            >
              回答を見直す・修正する
            </button>
          </div>
        </div>
      )}

      {/* Immediate feedback of the previous voted statement */}
      {lastResult && (
        <div className="card" style={{ borderLeft: "4px solid var(--agree-main)", animation: "slideUpBottom 0.25s ease-out" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem", marginBottom: "0.6rem" }}>
            <span style={{ fontWeight: 800, fontSize: "0.95rem", color: "var(--agree-text)" }}>
              ✓ 直前に投票した原則（#{lastResult.statementId}）の立場別集計
            </span>
            <button
              type="button"
              className="btn btn-sm btn-primary"
              onClick={() => onOpenStatement(lastResult.statementId)}
            >
              この原則の原体験を読む・書く ({lastResult.n_stories}件)
            </button>
          </div>
          <div style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--text-main)", marginBottom: "0.85rem" }}>
            「{lastResult.text}」
          </div>
          <PositionRateBars rates={lastResult.vote.by_position} onlyPrimary />
        </div>
      )}
    </div>
  );
}

export function PostTab({
  topicId,
  onOpenStatement,
  onCreated,
}: {
  topicId: number;
  onOpenStatement: (sid: number) => void;
  onCreated: () => void;
}) {
  const [rawText, setRawText] = useState("");
  const [converted, setConverted] = useState<ConvertResponse | null>(null);
  const [editText, setEditText] = useState("");
  const [includeStory, setIncludeStory] = useState(true);
  const [storyKind, setStoryKind] = useState<StoryKind>("present");
  const [storyText, setStoryText] = useState("");
  const [directText, setDirectText] = useState("");
  const [postResult, setPostResult] = useState<PostStatementResponse | null>(null);

  const convAct = useAction();
  const postAct = useAction();

  const handleConvert = () =>
    convAct.exec(async () => {
      setPostResult(null);
      const res = await api.convert(topicId, rawText);
      setConverted(res);
      if (res.principles.length > 0) {
        setEditText(res.principles[0].text);
      }
      if (res.story_draft) {
        setStoryKind(res.story_draft.kind);
        setStoryText(res.story_draft.text);
        setIncludeStory(true);
      } else {
        setStoryText("");
      }
    });

  const submitPrinciple = (text: string, origin: "user" | "ai_from_complaint", withStory: boolean) =>
    postAct.exec(async () => {
      const res = await api.postStatement(topicId, {
        text,
        origin,
        story: withStory && storyText.trim() ? { kind: storyKind, body: storyText } : undefined,
      });
      setPostResult(res);
      if (res.statement) {
        setRawText("");
        setConverted(null);
        setEditText("");
        setDirectText("");
        onCreated();
      }
    });

  const fillExample = (sampleText: string) => {
    setRawText(sampleText);
  };

  return (
    <div style={{ maxWidth: 740, margin: "0 auto" }}>
      {postResult && (
        <div className="card" style={{ borderLeft: "4px solid var(--brand-blue)" }}>
          {postResult.statement && (
            <div>
              <div style={{ fontWeight: 800, color: "var(--brand-blue)", marginBottom: "0.3rem" }}>
                ✓ 新しい原則 #{postResult.statement.id} として公開されました！
              </div>
              <p style={{ margin: "0.2rem 0 0.75rem", fontWeight: 700 }}>「{postResult.statement.text}」</p>
              <button
                type="button"
                className="btn btn-sm btn-primary"
                onClick={() => onOpenStatement(postResult.statement!.id)}
              >
                詳細・原体験を確認する
              </button>
            </div>
          )}
          {postResult.merged_into && (
            <div>
              <div style={{ fontWeight: 800, color: "var(--boundary-text)", marginBottom: "0.3rem" }}>
                ✓ 既存の原則と実質的に同一のため、統合されました
              </div>
              <p style={{ margin: "0.2rem 0 0.75rem" }}>
                あなたの声は既存の原則 #{postResult.merged_into.id}「{postResult.merged_into.text}」として投票されています。
              </p>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => onOpenStatement(postResult.merged_into!.id)}
              >
                統合先の原則を見る
              </button>
            </div>
          )}
          {postResult.rejected_reason && (
            <div className="error-box" style={{ marginBottom: 0 }}>
              投稿できませんでした：{postResult.rejected_reason}
            </div>
          )}
        </div>
      )}

      {/* Mode 1: AI Complaint / Story to Principle */}
      <div className="card" style={{ padding: "1.75rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.35rem" }}>
          <span style={{ fontSize: "1.3rem" }}>✨</span>
          <h3 style={{ margin: 0, fontSize: "1.18rem", fontWeight: 900, color: "var(--text-main)" }}>
            不満・モヤモヤ・現場の体験から原則を作る（AI変換）
          </h3>
        </div>
        <p style={{ fontSize: "0.88rem", color: "var(--text-muted)", margin: "0 0 0.85rem" }}>
          ルールや提言の文章を自力で書く必要はありません。日頃感じている不満や体験談をそのまま入力すると、AIが「投票できる原則」と「背景ストーリー」に整えて提案します。
        </p>

        {/* Quick Examples */}
        <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", marginBottom: "0.75rem" }}>
          <span style={{ fontSize: "0.78rem", fontWeight: 800, color: "var(--text-muted)", alignSelf: "center" }}>入力例：</span>
          <button
            type="button"
            className="btn btn-sm"
            style={{ fontSize: "0.78rem", padding: "0.2rem 0.55rem" }}
            onClick={() => fillExample("宿題でAIをどこまで使っていいか基準がなくて困っています。生徒が感想文をAI丸写しで提出し、自分の頭で考える力が失われるのではないかと心配です。")}
          >
            宿題での丸写し懸念
          </button>
          <button
            type="button"
            className="btn btn-sm"
            style={{ fontSize: "0.78rem", padding: "0.2rem 0.55rem" }}
            onClick={() => fillExample("教員の残業が多すぎるので、プリント作成や校務の定型文書はAIで自動化して現場の負担を減らすべきだと思います。")}
          >
            教員の校務効率化
          </button>
        </div>

        <textarea
          className="textarea"
          style={{ minHeight: "120px" }}
          placeholder="現場で困ったこと、不安に思うこと、こうなってほしいという希望を自由に書いてください…"
          value={rawText}
          onChange={(e) => setRawText(e.target.value)}
        />

        {convAct.error && <div className="error-box" style={{ marginTop: "0.75rem" }}>{convAct.error}</div>}

        <div style={{ marginTop: "0.85rem" }}>
          <button
            type="button"
            className="btn btn-primary"
            disabled={convAct.busy || rawText.trim().length < 4}
            onClick={handleConvert}
          >
            {convAct.busy ? "✨ AIが原則に変換中…" : "✨ 投票できる原則に変換する"}
          </button>
        </div>

        {converted && (
          <div className="card-subtle" style={{ marginTop: "1.25rem", background: "#ffffff", border: "1.5px solid var(--brand-blue)" }}>
            {converted.needs_clarification ? (
              <div>
                <strong style={{ color: "var(--boundary-text)" }}>もう少し具体的に教えてください</strong>
                <p style={{ margin: "0.3rem 0" }}>{converted.clarifying_question}</p>
              </div>
            ) : (
              <div>
                <div style={{ fontWeight: 800, fontSize: "0.96rem", color: "var(--text-main)", marginBottom: "0.5rem" }}>
                  変換された原則の候補（クリックで選択・編集可能）
                </div>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.75rem" }}>
                  {converted.principles.map((p, idx) => (
                    <button
                      key={idx}
                      type="button"
                      className={`btn btn-sm ${editText === p.text ? "btn-primary" : ""}`}
                      onClick={() => setEditText(p.text)}
                    >
                      候補{idx + 1}：{p.text}
                    </button>
                  ))}
                </div>

                <input
                  className="input"
                  style={{ fontWeight: 700 }}
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                />

                {storyText && (
                  <div style={{ marginTop: "1rem", paddingTop: "0.85rem", borderTop: "1px solid var(--border-subtle)" }}>
                    <label style={{ display: "flex", alignItems: "center", gap: "0.45rem", fontSize: "0.9rem", fontWeight: 800, color: "var(--text-main)" }}>
                      <input
                        type="checkbox"
                        checked={includeStory}
                        onChange={(e) => setIncludeStory(e.target.checked)}
                      />
                      背景の原体験（ストーリー）も一緒に紐づけて投稿する
                    </label>
                    {includeStory && (
                      <textarea
                        className="textarea"
                        style={{ marginTop: "0.5rem", fontSize: "0.9rem" }}
                        value={storyText}
                        onChange={(e) => setStoryText(e.target.value)}
                      />
                    )}
                  </div>
                )}

                {postAct.error && <div className="error-box" style={{ marginTop: "0.75rem" }}>{postAct.error}</div>}

                <div style={{ display: "flex", gap: "0.65rem", marginTop: "1rem" }}>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={postAct.busy || editText.trim().length < 4}
                    onClick={() => submitPrinciple(editText, "ai_from_complaint", includeStory)}
                  >
                    この原則と体験を公開する
                  </button>
                  <button
                    type="button"
                    className="btn"
                    onClick={() => setConverted(null)}
                  >
                    キャンセル
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Mode 2: Direct Input */}
      <div className="card" style={{ padding: "1.5rem" }}>
        <h3 style={{ margin: "0 0 0.4rem", fontSize: "1.05rem", fontWeight: 800 }}>
          直接「原則」を投稿する
        </h3>
        <p style={{ fontSize: "0.86rem", color: "var(--text-muted)", margin: "0 0 0.85rem" }}>
          すでに明確な提言文をお持ちの場合は、直接140字以内で投稿できます。
        </p>

        <input
          className="input"
          placeholder="例：〜の場合は、〜すべきだ（140字以内）"
          value={directText}
          onChange={(e) => setDirectText(e.target.value)}
        />

        <div style={{ marginTop: "0.85rem" }}>
          <button
            type="button"
            className="btn"
            disabled={postAct.busy || directText.trim().length < 4}
            onClick={() => submitPrinciple(directText, "user", false)}
          >
            直接投稿する
          </button>
        </div>
      </div>
    </div>
  );
}

export function StatementListTab({
  topicId,
  onOpenStatement,
}: {
  topicId: number;
  onOpenStatement: (sid: number) => void;
}) {
  const { data: items, loading, error } = useAsync(() => api.listStatements(topicId), [topicId]);
  const [filter, setFilter] = useState<Section | "all">("all");
  const [searchQuery, setSearchQuery] = useState("");

  if (loading && !items) return <div className="card" style={{ textAlign: "center" }}>読み込み中…</div>;
  if (error) return <div className="error-box">{error}</div>;

  const filteredBySection = (items ?? []).filter((it) => filter === "all" || it.section === filter);
  const list = filteredBySection.filter(
    (it) => !searchQuery.trim() || it.text.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  return (
    <div>
      {/* Export / Download Banner Card */}
      <div className="card" style={{ marginBottom: "1.25rem", padding: "1.1rem 1.3rem", background: "linear-gradient(135deg, rgba(37,99,235,0.05), rgba(139,92,246,0.05))", border: "1.5px solid rgba(37,99,235,0.18)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.75rem" }}>
          <div>
            <div style={{ fontWeight: 900, fontSize: "1rem", color: "var(--text-main)" }}>
              📊 投票・集計データのダウンロード
            </div>
            <div style={{ fontSize: "0.84rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
              各論点の賛成・反対数、立場別賛成率、投稿された原体験をExcel対応CSVでダウンロードできます。
            </div>
          </div>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <a
              href={`/api/topics/${topicId}/export/votes.csv`}
              download
              className="btn btn-sm btn-primary"
              style={{ textDecoration: "none", fontSize: "0.82rem", padding: "0.4rem 0.85rem", display: "inline-flex", alignItems: "center", gap: "0.35rem" }}
            >
              <span>📥</span>
              <span>投票集計 (CSV)</span>
            </a>
            <a
              href={`/api/topics/${topicId}/export/stories.csv`}
              download
              className="btn btn-sm"
              style={{ textDecoration: "none", fontSize: "0.82rem", padding: "0.4rem 0.85rem", display: "inline-flex", alignItems: "center", gap: "0.35rem", background: "#ffffff", border: "1px solid var(--border-subtle)" }}
            >
              <span>📥</span>
              <span>原体験一覧 (CSV)</span>
            </a>
          </div>
        </div>
      </div>

      {/* Search & Filter Header */}
      <div style={{ marginBottom: "1rem" }}>
        <input
          className="input"
          style={{ marginBottom: "0.75rem", borderRadius: "var(--radius-pill)" }}
          placeholder="🔍 原則のキーワード検索…"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />

        <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap" }}>
          <button
            type="button"
            className={`btn btn-sm ${filter === "all" ? "btn-primary" : ""}`}
            style={{ borderRadius: "var(--radius-pill)" }}
            onClick={() => setFilter("all")}
          >
            すべて ({items?.length ?? 0})
          </button>
          {SECTION_ORDER.map((sec) => {
            const count = (items ?? []).filter((i) => i.section === sec).length;
            return (
              <button
                key={sec}
                type="button"
                className={`btn btn-sm ${filter === sec ? "btn-primary" : ""}`}
                style={{ borderRadius: "var(--radius-pill)" }}
                onClick={() => setFilter(sec)}
              >
                {SECTION_LABEL[sec]} ({count})
              </button>
            );
          })}
        </div>
      </div>

      {filter !== "all" && (
        <div className="card-subtle" style={{ marginBottom: "1.25rem", padding: "0.85rem 1.1rem" }}>
          <div style={{ fontWeight: 800, fontSize: "0.94rem", color: "var(--text-main)", marginBottom: "0.2rem" }}>
            {SECTION_LABEL[filter]}
          </div>
          <div style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
            {SECTION_DESC[filter]}
          </div>
        </div>
      )}

      {/* Statement Cards */}
      <div style={{ display: "grid", gap: "0.85rem" }}>
        {list.map((st) => (
          <div
            key={st.id}
            className="card card-interactive"
            onClick={() => onOpenStatement(st.id)}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.45rem" }}>
              <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap", alignItems: "center" }}>
                <span className="badge" style={{ background: "var(--bg-app)" }}>#{st.id}</span>
                {st.section && (
                  <span className={`badge badge-${st.section}`}>{SECTION_LABEL[st.section]}</span>
                )}
                {ORIGIN_LABEL[st.origin] && <span className="badge">{ORIGIN_LABEL[st.origin]}</span>}
                {gapWords(st.gap) && (
                  <span className="badge" style={{ background: "var(--boundary-bg)", color: "var(--boundary-text)", border: "1px solid var(--boundary-border)" }}>
                    {gapWords(st.gap)}（差 {gapPoints(st.gap)}pt）
                  </span>
                )}
              </div>
              <span className="badge" style={{ color: "var(--brand-blue)" }}>
                原体験 {st.n_stories}件 →
              </span>
            </div>

            <div style={{ fontWeight: 800, fontSize: "1.08rem", color: "var(--text-main)", marginBottom: "0.65rem", lineHeight: 1.5 }}>
              {st.text}
            </div>

            <div style={{ fontSize: "0.85rem", color: "var(--text-muted)", display: "flex", gap: "1.2rem", flexWrap: "wrap", alignItems: "center" }}>
              <span>
                賛成 <strong style={{ color: "var(--agree-text)" }}>{st.counts.agree}</strong> ／ 反対 <strong style={{ color: "var(--disagree-text)" }}>{st.counts.disagree}</strong> ／ パス {st.counts.pass}
              </span>
              {st.my_vote !== null && (
                <span className="badge" style={{ background: st.my_vote === 1 ? "var(--agree-bg)" : st.my_vote === -1 ? "var(--disagree-bg)" : "var(--pass-bg)", color: st.my_vote === 1 ? "var(--agree-text)" : st.my_vote === -1 ? "var(--disagree-text)" : "var(--pass-text)" }}>
                  あなたの票：{st.my_vote === 1 ? "賛成" : st.my_vote === -1 ? "反対" : "パス"}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const PALETTE = ["#2563eb", "#059669", "#d97706", "#7c3aed", "#e11d48", "#0891b2"];

export function OpinionMapTab({
  topicId,
  onOpenStatement,
}: {
  topicId: number;
  onOpenStatement: (sid: number) => void;
}) {
  const { data: map, loading, error } = useAsync(() => api.getMap(topicId), [topicId]);
  const [lens, setLens] = useState<string>("cluster");
  const [selectedPoint, setSelectedPoint] = useState<null | {
    x: number;
    y: number;
    cluster: number;
    is_me: boolean;
    groups: Record<string, string>;
  }>(null);

  if (loading && !map) return <div className="card" style={{ textAlign: "center" }}>読み込み中…</div>;
  if (error) return <div className="error-box">{error}</div>;
  if (!map) return null;

  if (!map.available) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "2.5rem 1.5rem" }}>
        <h3 style={{ margin: "0 0 0.5rem" }}>意見マップはまだ表示できません</h3>
        <p style={{ color: "var(--text-muted)", margin: 0 }}>{map.reason}</p>
      </div>
    );
  }

  const xs = map.points.map((p) => p.x);
  const ys = map.points.map((p) => p.y);
  const minX = Math.min(...xs, -1);
  const maxX = Math.max(...xs, 1);
  const minY = Math.min(...ys, -1);
  const maxY = Math.max(...ys, 1);
  const scaleX = (x: number) => 50 + ((x - minX) / Math.max(1e-6, maxX - minX)) * 500;
  const scaleY = (y: number) => 310 - ((y - minY) / Math.max(1e-6, maxY - minY)) * 260;

  const groupLabels = Array.from(
    new Set(
      map.points.map((p) =>
        lens === "cluster" ? `意見グループ ${p.cluster + 1}` : (p.groups[lens] ?? "未選択"),
      ),
    ),
  );
  const colorOf = (label: string) => PALETTE[groupLabels.indexOf(label) % PALETTE.length];

  return (
    <div>
      <div className="card" style={{ padding: "1.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem", marginBottom: "1rem" }}>
          <div>
            <h3 style={{ margin: 0, fontSize: "1.2rem", fontWeight: 900, color: "var(--text-main)" }}>
              🗺️ 意見マップと「立場のレンズ」
            </h3>
            <div style={{ fontSize: "0.86rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
              参加者の配置は「投票パターン」のPCA（主成分分析）のみで決定されます。立場のレンズを切り替えることで、意見の塊と属性の重なりを検証できます。
            </div>
          </div>

          <select
            className="select"
            style={{ width: "auto", fontWeight: 700 }}
            value={lens}
            onChange={(e) => {
              setLens(e.target.value);
              setSelectedPoint(null);
            }}
          >
            <option value="cluster">🎨 色分け：意見グループ（投票のみ）</option>
            {map.dimensions.map((d) => (
              <option key={d.key} value={d.key}>
                🔍 立場のレンズ：{d.label}
              </option>
            ))}
          </select>
        </div>

        {/* Legend */}
        <div style={{ display: "flex", gap: "0.85rem", flexWrap: "wrap", marginBottom: "1rem", padding: "0.6rem 0.85rem", background: "var(--bg-app)", borderRadius: "var(--radius-md)" }}>
          {groupLabels.map((lbl) => (
            <span key={lbl} style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", fontSize: "0.85rem", fontWeight: 700 }}>
              <span
                style={{
                  width: 12,
                  height: 12,
                  borderRadius: "50%",
                  background: colorOf(lbl),
                  display: "inline-block",
                  boxShadow: "0 1px 4px rgba(0,0,0,0.2)",
                }}
              />
              {lbl}
            </span>
          ))}
        </div>

        {/* SVG Scatter Plot with Polis Group Areas */}
        <div style={{ position: "relative", width: "100%", overflow: "hidden", borderRadius: "var(--radius-md)", border: "1px solid var(--border-subtle)", background: "#ffffff" }}>
          <svg
            viewBox="0 0 600 360"
            style={{ width: "100%", height: "auto", display: "block", cursor: "crosshair" }}
          >
            {/* Cluster ambient background zones */}
            {map.clusters.map((cl) => {
              const cx = scaleX(cl.cx);
              const cy = scaleY(cl.cy);
              const color = PALETTE[cl.id % PALETTE.length];
              return (
                <circle
                  key={`zone-${cl.id}`}
                  cx={cx}
                  cy={cy}
                  r="65"
                  fill={color}
                  fillOpacity="0.08"
                  stroke={color}
                  strokeWidth="1.5"
                  strokeDasharray="4 4"
                  strokeOpacity="0.3"
                />
              );
            })}

            {/* Grid axes */}
            <line x1="50" y1="180" x2="550" y2="180" stroke="#f1f5f9" strokeWidth="1" strokeDasharray="4 4" />
            <line x1="300" y1="50" x2="300" y2="310" stroke="#f1f5f9" strokeWidth="1" strokeDasharray="4 4" />

            {/* Points */}
            {map.points.map((pt, idx) => {
              const lbl =
                lens === "cluster" ? `意見グループ ${pt.cluster + 1}` : (pt.groups[lens] ?? "未選択");
              const cx = scaleX(pt.x);
              const cy = scaleY(pt.y);
              const isSelected = selectedPoint === pt;
              return (
                <g key={idx} onClick={() => setSelectedPoint(pt)} style={{ cursor: "pointer" }}>
                  <circle
                    cx={cx}
                    cy={cy}
                    r={pt.is_me ? 10 : isSelected ? 8 : 6}
                    fill={colorOf(lbl)}
                    fillOpacity={pt.is_me ? 1 : 0.85}
                    stroke={pt.is_me ? "#0f172a" : isSelected ? "#000" : "#ffffff"}
                    strokeWidth={pt.is_me ? 3.5 : isSelected ? 2.5 : 1.5}
                  />
                  {pt.is_me && (
                    <g>
                      <circle cx={cx} cy={cy} r={16} fill="none" stroke="#2563eb" strokeWidth="2.5" opacity="0.7" />
                      <text x={cx + 14} y={cy + 5} fontSize="13" fontWeight="900" fill="#0f172a">
                        あなた
                      </text>
                    </g>
                  )}
                </g>
              );
            })}
          </svg>
        </div>

        {/* Selected Point Popover */}
        {selectedPoint && (
          <div className="card-subtle" style={{ marginTop: "1rem", background: "var(--brand-primary-light)", border: "1px solid var(--brand-primary-border)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontWeight: 800, color: "var(--brand-blue)" }}>
                {selectedPoint.is_me ? "👤 あなたのデータ" : "👤 参加者の属性と所属"}
              </span>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => setSelectedPoint(null)}
              >
                ✕ 閉じる
              </button>
            </div>
            <div style={{ marginTop: "0.35rem", fontSize: "0.88rem" }}>
              <div>・意見グループ：<strong>グループ {selectedPoint.cluster + 1}</strong></div>
              {Object.entries(selectedPoint.groups).map(([k, v]) => (
                <div key={k}>・{map.dimensions.find((d) => d.key === k)?.label ?? k}：<strong>{v}</strong></div>
              ))}
            </div>
          </div>
        )}

        {map.topic_dependency.length > 0 && (
          <div className="card-subtle" style={{ marginTop: "1.25rem", marginBottom: 0, padding: "0.85rem 1.1rem" }}>
            <strong style={{ fontSize: "0.9rem", color: "var(--text-main)" }}>
              📊 意見グループと立場の重なり度合い（正規化相互情報量 NMI）：
            </strong>
            <div style={{ display: "flex", gap: "0.85rem", flexWrap: "wrap", marginTop: "0.35rem", fontSize: "0.86rem" }}>
              {map.topic_dependency.map((td) => (
                <span key={td.dimension} className="badge" style={{ background: "#ffffff", border: "1px solid var(--border-subtle)" }}>
                  {td.label}：<strong>{td.nmi.toFixed(2)}</strong>（1に近いほど立場で意見が決まっている）
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Cluster Details */}
      <div className="grid-2">
        {map.clusters.map((cl) => (
          <div className="card" key={cl.id}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.6rem" }}>
              <span style={{ fontWeight: 800, fontSize: "1.05rem", color: "var(--text-main)" }}>
                意見グループ {cl.id + 1}
              </span>
              <span className="badge badge-consensus">{cl.size}名</span>
            </div>
            <div style={{ fontSize: "0.84rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
              このグループで特に賛成率が高かった原則：
            </div>
            {cl.top_statements.map((ts) => (
              <div
                key={ts.id}
                className="card-subtle"
                style={{ padding: "0.65rem 0.85rem", marginBottom: "0.5rem", cursor: "pointer" }}
                onClick={() => onOpenStatement(ts.id)}
              >
                <div style={{ fontSize: "0.92rem", fontWeight: 700, color: "var(--brand-blue)" }}>
                  {ts.text}
                </div>
                <div style={{ fontSize: "0.82rem", color: "var(--agree-text)", fontWeight: 800, marginTop: "0.2rem" }}>
                  賛成率 {pct(ts.agree_rate)}
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export function DiagnosisTab({
  topicId,
  onOpenStatement,
}: {
  topicId: number;
  onOpenStatement: (sid: number) => void;
}) {
  const { data: diag, loading, error } = useAsync(() => api.getDiagnosis(topicId), [topicId]);

  if (loading && !diag) return <div className="card" style={{ textAlign: "center" }}>読み込み中…</div>;
  if (error) return <div className="error-box">{error}</div>;
  if (!diag) return null;

  if (!diag.ready) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "3rem 1.5rem" }}>
        <div style={{ fontSize: "2.4rem", marginBottom: "0.5rem" }}>🎯</div>
        <h3 style={{ margin: "0 0 0.5rem" }}>あなたの立ち位置診断（ミクロ報酬）</h3>
        <p style={{ color: "var(--text-muted)", maxWidth: 480, margin: "0 auto" }}>
          立場によって意見が割れている重要論点にあと <strong>{diag.needed}問</strong> 投票すると、あなたの所属グループや同じ立場との一致度診断が表示されます。
        </p>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 840, margin: "0 auto" }}>
      <div className="card" style={{ padding: "2rem", borderTop: "4px solid var(--brand-blue)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: "0.5rem", marginBottom: "1rem" }}>
          <h2 style={{ fontSize: "1.35rem", fontWeight: 900, margin: 0, color: "var(--text-main)" }}>
            あなたの立ち位置診断結果
          </h2>
          {diag.cluster !== null && (
            <span className="badge badge-bridge" style={{ fontSize: "0.92rem", padding: "0.35rem 0.95rem" }}>
              所属：意見グループ {diag.cluster + 1}
            </span>
          )}
        </div>

        {diag.typicality ? (
          <div className="card-subtle" style={{ background: "var(--brand-primary-light)", border: "1px solid var(--brand-primary-border)", padding: "1.25rem" }}>
            <div style={{ fontWeight: 800, fontSize: "1.1rem", color: "var(--brand-blue)", marginBottom: "0.35rem" }}>
              立場によって意見が割れる {diag.typicality.total} 問中、{diag.typicality.matched} 問（{pct(diag.typicality.score)}）で「{diag.typicality.group_label}」の多数派と同じ回答でした
            </div>
            <div style={{ fontSize: "0.88rem", color: "var(--text-body)", lineHeight: 1.6 }}>
              あなたの意見には、同じ立場（{diag.typicality.group_label}）の人々と共鳴する部分と、あなた個人の経験や倫理観に基づいた独自の視点の両方が反映されています。
            </div>
          </div>
        ) : (
          <p style={{ fontSize: "0.9rem", color: "var(--text-muted)" }}>
            上部の「あなたの立場」を選択すると、同じ立場の人々との比較が表示されます。
          </p>
        )}

        {/* Distinctive viewpoints */}
        {diag.distinctive.length > 0 && (
          <div style={{ marginTop: "1.75rem" }}>
            <h3 style={{ fontSize: "1.08rem", fontWeight: 800, color: "var(--text-main)", marginBottom: "0.75rem" }}>
              💡 あなたならではの論点（同じ立場の多数派と異なる視点）
            </h3>
            <div style={{ display: "grid", gap: "0.65rem" }}>
              {diag.distinctive.map((d) => (
                <div
                  key={d.statement_id}
                  className="card card-interactive"
                  style={{ padding: "1rem", borderLeft: "4px solid var(--boundary-border)", background: "var(--boundary-bg)" }}
                  onClick={() => onOpenStatement(d.statement_id)}
                >
                  <div style={{ fontWeight: 800, fontSize: "0.98rem", color: "var(--text-main)" }}>
                    #{d.statement_id} {d.text}
                  </div>
                  <div style={{ fontSize: "0.86rem", color: "var(--boundary-text)", fontWeight: 700, marginTop: "0.3rem" }}>
                    「{d.group_label}」であなたと同じ「{d.my_vote === 1 ? "賛成" : "反対"}」を選んだ人はわずか {pct(d.group_vote_rate)} です。
                  </div>
                  <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
                    → なぜその考えに至ったのか、背景の体験談を書き添えてみましょう
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Reliving stories from same and other cluster */}
      <div className="grid-2" style={{ marginTop: "1.5rem" }}>
        <div>
          <div style={{ fontWeight: 800, fontSize: "1rem", color: "var(--text-main)", marginBottom: "0.75rem" }}>
            🤝 あなたと同じグループの人の原体験
          </div>
          {diag.stories.same ? (
            <StoryCardView story={diag.stories.same} />
          ) : (
            <div className="card-subtle" style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "0.88rem" }}>
              該当する体験談がまだありません
            </div>
          )}
        </div>

        <div>
          <div style={{ fontWeight: 800, fontSize: "1rem", color: "var(--text-main)", marginBottom: "0.75rem" }}>
            🌏 あなたと異なるグループの人の原体験（追体験）
          </div>
          {diag.stories.other ? (
            <StoryCardView story={diag.stories.other} />
          ) : (
            <div className="card-subtle" style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "0.88rem" }}>
              該当する体験談がまだありません
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function ReportTab({
  topicId,
  onOpenStatement,
  onChanged,
}: {
  topicId: number;
  onOpenStatement: (sid: number) => void;
  onChanged: () => void;
}) {
  const { data: versions, reload: reloadVersions } = useAsync(
    () => api.listReports(topicId),
    [topicId],
  );
  const [selectedVer, setSelectedVer] = useState<string | null>(null);
  const {
    data: report,
    loading,
    error,
    reload: reloadReport,
  } = useAsync(
    () => (selectedVer ? api.getReport(topicId, selectedVer) : api.getLatestReport(topicId)),
    [topicId, selectedVer],
  );
  const analyzeAct = useAction();
  const [copied, setCopied] = useState(false);

  const handleReanalyze = () =>
    analyzeAct.exec(async () => {
      await api.analyze(topicId);
      setSelectedVer(null);
      reloadVersions();
      reloadReport();
      onChanged();
    });

  const copyMarkdown = () => {
    if (report?.body_md) {
      navigator.clipboard.writeText(report.body_md);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const processedMd = (report?.body_md ?? "").replace(
    /\[S:(\d+)\]/g,
    "[\\[原則 #$1\\]](#stmt-$1)",
  );

  return (
    <div style={{ maxWidth: 840, margin: "0 auto" }}>
      {/* Action Header */}
      <div className="card" style={{ padding: "1.25rem 1.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.85rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.65rem", flexWrap: "wrap" }}>
            <span style={{ fontWeight: 800, fontSize: "1.05rem", color: "var(--text-main)" }}>
              成果物ドキュメント
            </span>
            {versions && versions.length > 0 && (
              <select
                className="select"
                style={{ width: "auto", fontWeight: 700 }}
                value={selectedVer ?? report?.version ?? ""}
                onChange={(e) => setSelectedVer(e.target.value)}
              >
                {versions.map((v) => (
                  <option key={v.version} value={v.version}>
                    バージョン v{v.version}（{formatDate(v.created_at)}）
                  </option>
                ))}
              </select>
            )}
            {report && (
              <span className="badge badge-bridge">
                編纂方式：{report.generator === "llm" ? "LLM編纂" : "数値ルール＋テンプレート編纂"}
              </span>
            )}
          </div>

          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button
              type="button"
              className="btn btn-sm"
              onClick={copyMarkdown}
            >
              {copied ? "✓ コピー完了" : "📋 Markdownをコピー"}
            </button>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={analyzeAct.busy}
              onClick={handleReanalyze}
            >
              {analyzeAct.busy ? "再編纂中…" : "🔄 最新の投票で成果物を更新"}
            </button>
          </div>
        </div>
        {analyzeAct.error && <div className="error-box" style={{ marginTop: "0.75rem" }}>{analyzeAct.error}</div>}
      </div>

      {loading && !report && <div className="card" style={{ textAlign: "center" }}>読み込み中…</div>}
      {error && <div className="error-box">{error}</div>}

      {/* Report Document Body */}
      {report && (
        <div className="card" style={{ padding: "2.5rem 2rem", background: "#ffffff", boxShadow: "var(--shadow-float)" }}>
          <ReactMarkdown
            components={{
              a: ({ href, children }) => {
                if (href && href.startsWith("#stmt-")) {
                  const sid = Number(href.replace("#stmt-", ""));
                  return (
                    <a
                      href={href}
                      className="badge badge-consensus"
                      style={{ cursor: "pointer", textDecoration: "none", margin: "0 0.2rem" }}
                      onClick={(e) => {
                        e.preventDefault();
                        onOpenStatement(sid);
                      }}
                    >
                      {children}
                    </a>
                  );
                }
                return <a href={href}>{children}</a>;
              },
            }}
          >
            {processedMd}
          </ReactMarkdown>
        </div>
      )}
    </div>
  );
}
