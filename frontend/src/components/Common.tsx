import { useState } from "react";
import {
  api,
  type AnonymizeResponse,
  type BridgesResponse,
  type PositionRate,
  type ReactionKind,
  type Stance,
  type StoryCard,
  type StoryKind,
  type VoteValue,
} from "../api";
import { useAction, useAsync } from "../hooks";
import {
  gapPoints,
  gapWords,
  ORIGIN_LABEL,
  SECTION_DESC,
  SECTION_LABEL,
  STORY_KIND_LABEL,
} from "../labels";

export function PositionRateBars({
  rates,
  onlyPrimary = false,
}: {
  rates: PositionRate[];
  onlyPrimary?: boolean;
}) {
  if (!rates.length) return null;
  const byDim = new Map<string, PositionRate[]>();
  for (const r of rates) {
    const list = byDim.get(r.dimension_label) ?? [];
    list.push(r);
    byDim.set(r.dimension_label, list);
  }
  const entries = Array.from(byDim.entries());
  const shown = onlyPrimary ? entries.slice(0, 1) : entries;

  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      {shown.map(([dimLabel, items]) => (
        <div key={dimLabel}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
            <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.03em" }}>
              立場別の賛成率（{dimLabel}）
            </span>
            <span style={{ fontSize: "0.78rem", color: "var(--text-subtle)" }}>
              緑: 賛成 / 赤: 反対
            </span>
          </div>

          <div style={{ display: "grid", gap: "0.5rem" }}>
            {items.map((item) => {
              const agreePct = item.agree_rate !== null ? Math.round(item.agree_rate * 100) : 0;
              const disagreePct = 100 - agreePct;
              return (
                <div key={item.group} className="position-bar-card">
                  <div className="position-bar-header">
                    <span className="position-bar-label">{item.group_label}</span>
                    <span className="position-bar-stat">
                      {item.hidden || item.agree_rate === null ? (
                        <span style={{ color: "var(--text-muted)", fontSize: "0.8rem", fontWeight: 500 }}>
                          🔒 10人未満（プライバシー保護のため非表示）
                        </span>
                      ) : (
                        <span>
                          賛成 <strong style={{ color: "var(--agree-text)" }}>{agreePct}%</strong> / 反対 {disagreePct}% ({item.n}名)
                        </span>
                      )}
                    </span>
                  </div>

                  {!item.hidden && item.agree_rate !== null && (
                    <div className="progress-track">
                      <div className="progress-agree" style={{ width: `${agreePct}%` }} />
                      <div className="progress-disagree" style={{ width: `${disagreePct}%` }} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

export function StoryCardView({
  story,
  onReacted,
}: {
  story: StoryCard;
  onReacted?: (updated: { reactions: StoryCard["reactions"]; my_reactions: ReactionKind[] }) => void;
}) {
  const [reactions, setReactions] = useState(story.reactions);
  const [myReacs, setMyReacs] = useState<ReactionKind[]>(story.my_reactions);
  const { busy, exec } = useAction();

  const handleReact = (kind: ReactionKind) =>
    exec(async () => {
      const res = await api.react(story.id, kind);
      setReactions(res.reactions);
      setMyReacs(res.my_reactions);
      onReacted?.(res);
    });

  return (
    <div
      className="card"
      style={{
        padding: "1.1rem",
        marginBottom: "0.85rem",
        borderLeft: story.is_boundary ? "4px solid var(--boundary-gold)" : "4px solid var(--brand-primary)",
        background: story.is_boundary ? "var(--boundary-bg)" : "#ffffff",
      }}
    >
      <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap", marginBottom: "0.55rem", alignItems: "center" }}>
        <span className="badge">{STORY_KIND_LABEL[story.kind]}</span>
        {story.author_position_label && (
          <span className="badge" style={{ background: "#ffffff", border: "1px solid var(--border-subtle)", color: "var(--text-main)" }}>
            立場：<strong>{story.author_position_label}</strong>
          </span>
        )}
        {story.is_boundary && (
          <span className="badge badge-boundary" title="同じ立場の多数派とは異なる投票をした方の貴重な視点">
            ★ 立場を越えた体験（境界人）
          </span>
        )}
      </div>

      <div style={{ fontWeight: 700, fontSize: "0.98rem", color: "var(--text-main)", marginBottom: "0.4rem", lineHeight: 1.5 }}>
        {story.summary}
      </div>

      {story.body !== story.summary && (
        <div style={{ fontSize: "0.9rem", color: "var(--text-body)", marginBottom: "0.85rem", lineHeight: 1.6, whiteSpace: "pre-line" }}>
          {story.body}
        </div>
      )}

      <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
        <button
          type="button"
          className={`btn btn-sm ${myReacs.includes("resonate") ? "btn-primary" : ""}`}
          disabled={busy}
          onClick={() => handleReact("resonate")}
        >
          ❤️ 共感 ({reactions.resonate})
        </button>
        <button
          type="button"
          className={`btn btn-sm ${myReacs.includes("understand") ? "btn-vote-agree" : ""}`}
          disabled={busy}
          onClick={() => handleReact("understand")}
          title="意見そのものには賛成しなくても、その立場でそう考える理由は理解できたときに押します"
        >
          💡 理解できた・理由はわかった ({reactions.understand})
        </button>
      </div>
    </div>
  );
}

export function StatementModal({
  statementId,
  onClose,
  onChanged,
}: {
  statementId: number;
  onClose: () => void;
  onChanged?: () => void;
}) {
  const { data: detail, loading, error, reload } = useAsync(
    () => api.getStatement(statementId),
    [statementId],
  );
  const voteAct = useAction();
  const bridgeAct = useAction();
  const storyAct = useAction();

  const [bridgeResult, setBridgeResult] = useState<BridgesResponse | null>(null);
  const [kind, setKind] = useState<StoryKind>("present");
  const [stance, setStance] = useState<Stance>("supports");
  const [storyBody, setStoryBody] = useState("");
  const [anonPreview, setAnonPreview] = useState<AnonymizeResponse | null>(null);

  const doVote = (val: VoteValue) =>
    voteAct.exec(async () => {
      await api.vote(statementId, val);
      reload();
      onChanged?.();
    });

  const doAnonymize = () =>
    storyAct.exec(async () => {
      const res = await api.anonymize(storyBody);
      setAnonPreview(res);
      setStoryBody(res.masked_body);
    });

  const doPostStory = () =>
    storyAct.exec(async () => {
      await api.postStory(statementId, {
        kind,
        body: storyBody,
        summary: anonPreview?.summary,
        stance,
      });
      setStoryBody("");
      setAnonPreview(null);
      reload();
      onChanged?.();
    });

  const doBridges = () =>
    bridgeAct.exec(async () => {
      const res = await api.bridges(statementId);
      setBridgeResult(res);
      onChanged?.();
    });

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <span style={{ fontWeight: 800, fontSize: "0.95rem", color: "var(--brand-primary)" }}>
              原則 #{statementId}
            </span>
            {detail?.stats && (
              <span className={`badge badge-${detail.stats.section}`}>
                {SECTION_LABEL[detail.stats.section]}
              </span>
            )}
            {detail && ORIGIN_LABEL[detail.origin] && (
              <span className="badge">{ORIGIN_LABEL[detail.origin]}</span>
            )}
          </div>
          <button type="button" className="btn btn-sm" onClick={onClose} style={{ borderRadius: "50%", width: 32, height: 32, padding: 0 }}>
            ✕
          </button>
        </div>

        {loading && <p style={{ color: "var(--text-muted)" }}>読み込み中…</p>}
        {error && <div className="error-box">{error}</div>}

        {detail && (
          <>
            <h2 style={{ fontSize: "1.35rem", fontWeight: 800, color: "var(--text-main)", margin: "0.25rem 0 0.85rem", lineHeight: 1.5 }}>
              {detail.text}
            </h2>

            {detail.stats && (
              <div className="card-subtle" style={{ margin: "0.75rem 0 1.25rem", padding: "0.85rem 1rem" }}>
                <div style={{ fontWeight: 600, fontSize: "0.88rem", color: "var(--text-main)", marginBottom: "0.2rem" }}>
                  {SECTION_LABEL[detail.stats.section]}
                  {gapWords(detail.stats.gap) && `（${gapWords(detail.stats.gap)}：最大差 ${gapPoints(detail.stats.gap)}pt）`}
                </div>
                <div style={{ fontSize: "0.84rem", color: "var(--text-muted)" }}>
                  {SECTION_DESC[detail.stats.section]}
                </div>
              </div>
            )}

            {/* Voting Bar in Modal */}
            <div style={{ display: "flex", gap: "0.65rem", flexWrap: "wrap", marginBottom: "1.5rem" }}>
              <button
                type="button"
                className={`btn ${detail.my_vote === 1 ? "btn-vote-agree" : ""}`}
                style={{ flex: 1, minWidth: 120, fontWeight: 700 }}
                disabled={voteAct.busy}
                onClick={() => doVote(1)}
              >
                👍 賛成 ({detail.counts.agree})
              </button>
              <button
                type="button"
                className={`btn ${detail.my_vote === -1 ? "btn-vote-disagree" : ""}`}
                style={{ flex: 1, minWidth: 120, fontWeight: 700 }}
                disabled={voteAct.busy}
                onClick={() => doVote(-1)}
              >
                👎 反対 ({detail.counts.disagree})
              </button>
              <button
                type="button"
                className={`btn ${detail.my_vote === 0 ? "btn-vote-pass" : ""}`}
                style={{ flex: 1, minWidth: 120, fontWeight: 700 }}
                disabled={voteAct.busy}
                onClick={() => doVote(0)}
              >
                ➡️ パス ({detail.counts.pass})
              </button>
            </div>

            {/* Position Breakdown */}
            <div style={{ marginBottom: "1.5rem" }}>
              <PositionRateBars rates={detail.by_position} />
            </div>

            {/* Bridge Generation for Divergence */}
            {detail.stats?.section === "divergence" && (
              <div className="card-subtle" style={{ borderLeft: "4px solid var(--bridge-main)", background: "var(--bridge-bg)", marginBottom: "1.5rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                  <div>
                    <strong style={{ color: "var(--bridge-main)", fontSize: "0.95rem" }}>✨ 条件付き合意案（橋渡し原則）の提案</strong>
                    <div style={{ fontSize: "0.85rem", color: "var(--text-body)", marginTop: "0.2rem" }}>
                      賛成側・反対側双方の体験談から懸念を抽出し、歩み寄れる条件付きの原則案をAIが作成して投票にかけます。
                    </div>
                  </div>
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    disabled={bridgeAct.busy}
                    onClick={doBridges}
                    style={{ background: "var(--bridge-main)", borderColor: "var(--bridge-main)" }}
                  >
                    {bridgeAct.busy ? "生成中…" : "条件付き合意案を提案させる"}
                  </button>
                </div>
                {bridgeAct.error && <div className="error-box" style={{ marginTop: "0.75rem" }}>{bridgeAct.error}</div>}
                {bridgeResult && (
                  <div style={{ marginTop: "0.85rem", fontSize: "0.88rem", borderTop: "1px solid var(--bridge-border)", paddingTop: "0.75rem" }}>
                    {bridgeResult.concerns && (
                      <div style={{ marginBottom: "0.5rem", color: "var(--text-body)" }}>
                        <div>・{bridgeResult.concerns.support_side}</div>
                        <div>・{bridgeResult.concerns.oppose_side}</div>
                      </div>
                    )}
                    <div style={{ fontWeight: 700, color: "var(--bridge-main)" }}>{bridgeResult.message}</div>
                    {bridgeResult.created.map((c) => (
                      <div key={c.id} style={{ marginTop: "0.35rem", fontWeight: 600 }}>
                        → 新規原則 #{c.id}：「{c.text}」
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Lived Experiences Breakdown */}
            <div style={{ marginTop: "1.5rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.85rem" }}>
                <h3 style={{ fontSize: "1.1rem", fontWeight: 800, color: "var(--text-main)", margin: 0 }}>
                  背景の原体験（なぜその立場でそう考えるのか）
                </h3>
                <span style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
                  計 {detail.stories.supports.length + detail.stories.opposes.length + detail.stories.context.length} 件
                </span>
              </div>

              <div className="grid-2">
                <div>
                  <div style={{ fontSize: "0.9rem", fontWeight: 700, color: "var(--agree-text)", marginBottom: "0.6rem", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                    <span>👍 賛成側の原体験</span>
                    <span className="badge badge-consensus">{detail.stories.supports.length}</span>
                  </div>
                  {detail.stories.supports.length === 0 ? (
                    <div className="card-subtle" style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem" }}>
                      まだ賛成側の体験談がありません
                    </div>
                  ) : (
                    detail.stories.supports.map((s) => (
                      <StoryCardView key={s.id} story={s} onReacted={() => reload()} />
                    ))
                  )}
                </div>

                <div>
                  <div style={{ fontSize: "0.9rem", fontWeight: 700, color: "var(--disagree-text)", marginBottom: "0.6rem", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                    <span>👎 反対側の原体験</span>
                    <span className="badge badge-divergence">{detail.stories.opposes.length}</span>
                  </div>
                  {detail.stories.opposes.length === 0 ? (
                    <div className="card-subtle" style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem" }}>
                      まだ反対側の体験談がありません
                    </div>
                  ) : (
                    detail.stories.opposes.map((s) => (
                      <StoryCardView key={s.id} story={s} onReacted={() => reload()} />
                    ))
                  )}
                </div>
              </div>

              {detail.stories.context.length > 0 && (
                <div style={{ marginTop: "1rem" }}>
                  <div style={{ fontSize: "0.9rem", fontWeight: 700, color: "var(--text-muted)", marginBottom: "0.5rem" }}>
                    状況・背景の共有 ({detail.stories.context.length})
                  </div>
                  {detail.stories.context.map((s) => (
                    <StoryCardView key={s.id} story={s} onReacted={() => reload()} />
                  ))}
                </div>
              )}
            </div>

            {/* Story Submission Card */}
            <div className="card" style={{ marginTop: "1.75rem", background: "var(--bg-app)", border: "1.5px dashed var(--border-focus)" }}>
              <h4 style={{ margin: "0 0 0.4rem", fontSize: "1rem", fontWeight: 800, color: "var(--text-main)" }}>
                ✍️ あなたの原体験・未来シナリオを書き添える
              </h4>
              <p style={{ fontSize: "0.84rem", color: "var(--text-muted)", margin: "0 0 0.85rem" }}>
                数字だけの賛否ではなく、「現場でこんなことがあった」「こんな未来が心配だ」という体験を共有することで、他の立場の人にあなたの視点を追体験してもらえます。
              </p>

              <div style={{ display: "flex", gap: "0.65rem", flexWrap: "wrap", marginBottom: "0.75rem" }}>
                <select
                  className="select"
                  style={{ width: "auto", fontWeight: 600 }}
                  value={stance}
                  onChange={(e) => setStance(e.target.value as Stance)}
                >
                  <option value="supports">👍 賛成の根拠となる体験</option>
                  <option value="opposes">👎 反対の根拠となる体験</option>
                  <option value="context">📋 中立的な背景・現場の状況</option>
                </select>
                <select
                  className="select"
                  style={{ width: "auto", fontWeight: 600 }}
                  value={kind}
                  onChange={(e) => setKind(e.target.value as StoryKind)}
                >
                  <option value="past">過去の具体的な体験</option>
                  <option value="present">現在の現場のリアル</option>
                  <option value="future">危惧・期待する未来シナリオ</option>
                </select>
              </div>

              <textarea
                className="textarea"
                placeholder="現場で実際にあった出来事や、その立場だからこそ感じる懸念・背景を書いてください（固有名詞は自動で伏せられます）"
                value={storyBody}
                onChange={(e) => setStoryBody(e.target.value)}
              />

              {anonPreview && (
                <div className="card-subtle" style={{ marginTop: "0.65rem", fontSize: "0.85rem", background: "#ffffff" }}>
                  <div style={{ fontWeight: 700, color: "var(--brand-primary)" }}>匿名化プレビュー</div>
                  <div style={{ margin: "0.2rem 0" }}>要約：「{anonPreview.summary}」</div>
                  {anonPreview.masked_items.length > 0 && (
                    <div style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>
                      伏せた項目：{anonPreview.masked_items.join("、")}
                    </div>
                  )}
                </div>
              )}

              {storyAct.error && <div className="error-box" style={{ marginTop: "0.75rem" }}>{storyAct.error}</div>}

              <div style={{ display: "flex", gap: "0.65rem", marginTop: "0.85rem" }}>
                <button
                  type="button"
                  className="btn"
                  disabled={storyAct.busy || storyBody.trim().length < 4}
                  onClick={doAnonymize}
                >
                  🔍 匿名化・要約を確認
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={storyAct.busy || storyBody.trim().length < 4}
                  onClick={doPostStory}
                >
                  この体験談を投稿する
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
