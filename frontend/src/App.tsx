import { useState } from "react";
import { BrowserRouter, Link, Route, Routes, useNavigate, useParams, useLocation } from "react-router-dom";
import { api } from "./api";
import { AuthProvider, useAuth } from "./auth";
import { clickable, Loading, StatementModal, useModal } from "./components/Common";
import {
  DiagnosisTab,
  OpinionMapTab,
  PositionSelector,
  PostTab,
  ReportTab,
  StatementListTab,
  VoteTab,
} from "./components/TopicViews";
import { useAction, useAsync } from "./hooks";
import { CONTRIBUTION_LABEL, formatDate } from "./labels";

function ProfileModal({ onClose }: { onClose: () => void }) {
  const { user, updateProfile } = useAuth();
  const { data: meta } = useAsync(() => api.getMeta(), []);
  const [handle, setHandle] = useState(user?.handle ?? "参加者");
  const [attrs, setAttrs] = useState<Record<string, string>>(user?.attributes ?? {});
  const { busy, error, exec } = useAction();
  useModal(onClose);

  const submit = () =>
    exec(async () => {
      await updateProfile(handle.trim() || "匿名参加者", attrs);
      onClose();
    });

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" role="dialog" aria-modal="true" style={{ maxWidth: 520 }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.85rem" }}>
          <h3 style={{ margin: 0, fontSize: "1.15rem", fontWeight: 800 }}>👤 プロフィールの変更</h3>
          <button type="button" className="btn btn-sm" aria-label="閉じる" onClick={onClose}>✕</button>
        </div>
        <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginBottom: "1rem" }}>
          あなたの投票履歴や参加データ（ID）を維持したまま、表示名や属性を更新できます。
        </p>

        <div style={{ marginBottom: "1rem" }}>
          <label style={{ fontSize: "0.85rem", fontWeight: 800, display: "block", marginBottom: "0.35rem" }}>
            表示名（ニックネーム）
          </label>
          <input
            className="input"
            value={handle}
            onChange={(e) => setHandle(e.target.value)}
            placeholder="例：教員A / 学生B"
          />
        </div>

        {meta?.attributes.map((a) => (
          <div key={a.key} style={{ marginBottom: "0.75rem" }}>
            <label style={{ fontSize: "0.85rem", fontWeight: 800, display: "block", marginBottom: "0.35rem" }}>
              {a.label}（任意）
            </label>
            <select
              className="select"
              value={attrs[a.key] ?? ""}
              onChange={(e) => setAttrs({ ...attrs, [a.key]: e.target.value })}
            >
              <option value="">選択しない（スキップ）</option>
              {a.options.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          </div>
        ))}

        {error && <div className="error-box" style={{ marginBottom: "0.75rem" }}>{error}</div>}

        <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
          <button type="button" className="btn" onClick={onClose}>キャンセル</button>
          <button type="button" className="btn btn-primary" disabled={busy} onClick={submit}>
            {busy ? "保存中…" : "変更を保存する"}
          </button>
        </div>
      </div>
    </div>
  );
}

function RegisterPanel({ onDone }: { onDone?: () => void }) {
  const { user, updateProfile, login } = useAuth();
  const { data: meta } = useAsync(() => api.getMeta(), []);
  const [handle, setHandle] = useState(user?.handle && user.handle !== "ゲスト参加者" ? user.handle : "");
  const [attrs, setAttrs] = useState<Record<string, string>>(user?.attributes ?? {});
  const { busy, error, exec } = useAction();

  const submit = () =>
    exec(async () => {
      const cleanHandle = handle.trim() || (user?.handle && user.handle !== "ゲスト参加者" ? user.handle : "匿名参加者");
      if (user) {
        // すでに端末アカウントがある場合は同一IDのまま更新（多重参加を完全防止）
        await updateProfile(cleanHandle, attrs);
      } else {
        const res = await api.createUser(cleanHandle, attrs);
        login(res.user, res.token);
      }
      onDone?.();
    });

  return (
    <div className="card" style={{ borderLeft: "4px solid var(--brand-blue)", background: "#ffffff", marginBottom: "1rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.4rem" }}>
        <span style={{ fontSize: "1.2rem" }}>👤</span>
        <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 800, color: "var(--text-main)" }}>
          参加プロフィールの設定（匿名参加可）
        </h3>
      </div>
      <p style={{ fontSize: "0.86rem", color: "var(--text-muted)", margin: "0 0 1rem", lineHeight: 1.6 }}>
        入力された年代や役割などの属性は、10名以上の集計グループ単位での統計表示（立場間ギャップの可視化）のみに使用され、あなた個人の投票内容が公開されることはありません。
      </p>

      <div className="grid-2" style={{ marginBottom: "1rem" }}>
        <div>
          <label style={{ fontSize: "0.85rem", fontWeight: 800, display: "block", marginBottom: "0.35rem" }}>
            表示名（ニックネーム）
          </label>
          <input
            className="input"
            value={handle}
            onChange={(e) => setHandle(e.target.value)}
            placeholder="例：教員A / 学生B"
          />
        </div>
        {meta?.attributes.map((a) => (
          <div key={a.key}>
            <label style={{ fontSize: "0.85rem", fontWeight: 800, display: "block", marginBottom: "0.35rem" }}>
              {a.label}（任意）
            </label>
            <select
              className="select"
              value={attrs[a.key] ?? ""}
              onChange={(e) => setAttrs({ ...attrs, [a.key]: e.target.value })}
            >
              <option value="">選択しない（スキップ）</option>
              {a.options.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          </div>
        ))}
      </div>

      {error && <div className="error-box">{error}</div>}

      <button type="button" className="btn btn-primary" disabled={busy} onClick={submit}>
        {busy ? "設定中…" : "この設定で参加する →"}
      </button>
    </div>
  );
}

function TopicListPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const { data: topics, loading, error, reload } = useAsync(() => api.listTopics(), []);
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [axes, setAxes] = useState<{ name: string; options: string[]; why_divergent?: string }[]>([]);
  const [statementsText, setStatementsText] = useState("");
  const suggestAct = useAction();
  const suggestStmtsAct = useAction();
  const createAct = useAction();

  const handleOpenCreate = async () => {
    if (!user) {
      try {
        const randId = Math.floor(Math.random() * 900) + 100;
        const res = await api.createUser(`トピック発起人${randId}`, {});
        login(res.user, res.token);
      } catch (err) {
        console.error("Auto login error", err);
      }
    }
    setShowCreate((s) => !s);
  };

  const doSuggestAxes = () =>
    suggestAct.exec(async () => {
      const res = await api.suggestAxes(title, desc);
      setAxes(res.axes);
    });

  const doSuggestStatements = () =>
    suggestStmtsAct.exec(async () => {
      const res = await api.suggestStatements(title, desc);
      setStatementsText(res.statements.join("\n"));
    });

  const handleAddAxis = () => {
    setAxes([
      ...axes,
      {
        name: `立場の軸 ${axes.length + 1}`,
        options: ["推進・活用する側", "慎重・影響を受ける側", "中立・市民", "当てはまらない"],
        why_divergent: "立場による利害・リスクの違いを可視化するため",
      },
    ]);
  };

  const doCreate = () =>
    createAct.exec(async () => {
      const parsedStatements = statementsText
        .split("\n")
        .map((s) => s.trim())
        .filter((s) => s.length >= 4);

      const created = await api.createTopic(
        title,
        desc,
        axes.map((a) => ({ name: a.name, options: a.options })),
        parsedStatements,
      );
      setShowCreate(false);
      reload();
      navigate(`/topics/${created.id}`);
    });

  return (
    <div>
      {/* Hero Banner */}
      <div className="topic-hero">
        <div style={{ display: "inline-flex", gap: "0.5rem", alignItems: "center", marginBottom: "0.5rem" }}>
          <span className="badge" style={{ background: "#ffffff", color: "var(--brand-blue)", border: "1.5px solid var(--brand-blue)" }}>
            Polis型 熟議 × 原体験プラットフォーム
          </span>
          <span className="badge">成果型SNS</span>
        </div>
        <h1 className="topic-title">
          「誰が・どの立場から・どんな体験をもとにそう主張しているのか」を可視化する
        </h1>
        <p className="topic-desc">
          人の意見は置かれた立場（利害・役割・環境）によって決まる側面があります。
          言い争うのではなく、短い原則への投票と背景ストーリーの追体験を通じて、立場ごとの分岐点と共通原則を明らかにした成果物を自動編纂します。
        </p>
      </div>

      {!user && <RegisterPanel />}

      {/* Actions bar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem", flexWrap: "wrap", gap: "0.75rem" }}>
        <div>
          <h2 style={{ fontSize: "1.25rem", fontWeight: 900, margin: 0, color: "var(--text-main)" }}>
            議論トピック一覧
          </h2>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          style={{ fontSize: "0.95rem", padding: "0.55rem 1.2rem", boxShadow: "0 2px 8px rgba(37,99,235,0.25)" }}
          onClick={handleOpenCreate}
        >
          {showCreate ? "✕ フォームを閉じる" : "＋ 新しい議論トピックを立ち上げる"}
        </button>
      </div>

      {/* Create Topic Modal / Box */}
      {showCreate && (
        <div className="card" style={{ padding: "1.75rem", borderLeft: "5px solid var(--brand-blue)", marginBottom: "1.5rem", background: "#ffffff", boxShadow: "0 4px 20px rgba(0,0,0,0.06)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
            <h3 style={{ margin: 0, fontSize: "1.25rem", fontWeight: 900, color: "var(--text-main)" }}>
              🌱 新しい議論トピックを立ち上げる
            </h3>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => setShowCreate(false)}
            >
              ✕ 閉じる
            </button>
          </div>

          <p style={{ color: "var(--text-muted)", fontSize: "0.88rem", marginTop: 0, marginBottom: "1.25rem" }}>
            テーマと説明を入力するだけで、AIが最適な「立場の軸」と「初期の投票論点」を自動提案します。
          </p>

          {/* 1. Title */}
          <div style={{ marginBottom: "1rem" }}>
            <label style={{ fontSize: "0.9rem", fontWeight: 800, display: "block", marginBottom: "0.35rem" }}>
              ① トピックのタイトル <span style={{ color: "#ef4444" }}>*</span>
            </label>
            <input
              className="input"
              style={{ fontSize: "1rem", fontWeight: 700 }}
              placeholder="例：週休3日制の導入における課題と現場の合意点"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>

          {/* 2. Description */}
          <div style={{ marginBottom: "1.25rem" }}>
            <label style={{ fontSize: "0.9rem", fontWeight: 800, display: "block", marginBottom: "0.35rem" }}>
              ② 説明・問いかけ（背景や参加者に持ち寄ってほしいこと）
            </label>
            <textarea
              className="textarea"
              style={{ minHeight: "85px" }}
              placeholder="例：生産性向上と業務のしわ寄せ、給与への影響など、各立場（経営者・社員・顧客）の生の体験を持ち寄り、現実的な運用ルールを探ります。"
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
            />
          </div>

          {/* 3. Position Axes */}
          <div style={{ marginBottom: "1.5rem", padding: "1.1rem", background: "var(--bg-app)", borderRadius: "var(--radius-md)", border: "1px solid var(--border-subtle)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem", marginBottom: "0.75rem" }}>
              <div>
                <label style={{ fontSize: "0.92rem", fontWeight: 900, color: "var(--text-main)" }}>
                  ③ 立場の軸（意見の違いを検証するレンズ）
                </label>
                <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                  参加者がどの立場から投票しているかを比較するための属性軸です（最大3軸）。
                </div>
              </div>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button
                  type="button"
                  className="btn btn-sm btn-primary"
                  disabled={suggestAct.busy || title.trim().length < 2}
                  onClick={doSuggestAxes}
                >
                  {suggestAct.busy ? "✨ AIが考案中…" : "✨ AIに軸を自動提案してもらう"}
                </button>
                <button
                  type="button"
                  className="btn btn-sm"
                  onClick={handleAddAxis}
                >
                  ＋ 軸を手動追加
                </button>
              </div>
            </div>

            {axes.length === 0 ? (
              <div style={{ padding: "1rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.86rem", background: "#ffffff", borderRadius: "var(--radius-sm)" }}>
                上の「✨ AIに軸を自動提案してもらう」を押すか、「＋ 軸を手動追加」で立場を設定できます。
                （未設定の場合は公開時にAIが自動生成します）
              </div>
            ) : (
              <div style={{ display: "grid", gap: "0.75rem" }}>
                {axes.map((ax, idx) => (
                  <div key={idx} style={{ background: "#ffffff", padding: "0.85rem", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-subtle)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.35rem" }}>
                      <span style={{ fontSize: "0.82rem", fontWeight: 800, color: "var(--brand-blue)" }}>
                        軸 {idx + 1}：名前
                      </span>
                      <button
                        type="button"
                        style={{ border: "none", background: "none", color: "#ef4444", fontSize: "0.78rem", cursor: "pointer", fontWeight: 700 }}
                        onClick={() => setAxes(axes.filter((_, i) => i !== idx))}
                      >
                        ✕ 削除
                      </button>
                    </div>
                    <input
                      className="input"
                      style={{ marginBottom: "0.5rem", fontWeight: 700 }}
                      value={ax.name}
                      onChange={(e) => {
                        const copy = [...axes];
                        copy[idx] = { ...ax, name: e.target.value };
                        setAxes(copy);
                      }}
                      placeholder="例：このテーマとの関わり方"
                    />
                    <div style={{ fontSize: "0.82rem", fontWeight: 800, color: "var(--text-muted)", marginBottom: "0.25rem" }}>
                      選択肢（カンマ区切りで入力）
                    </div>
                    <input
                      className="input"
                      value={ax.options.join(", ")}
                      onChange={(e) => {
                        const copy = [...axes];
                        copy[idx] = {
                          ...ax,
                          options: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
                        };
                        setAxes(copy);
                      }}
                      placeholder="例：推進側, 慎重側, 一般市民, 当てはまらない"
                    />
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 4. Initial Statements */}
          <div style={{ marginBottom: "1.5rem", padding: "1.1rem", background: "var(--bg-app)", borderRadius: "var(--radius-md)", border: "1px solid var(--border-subtle)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem", marginBottom: "0.75rem" }}>
              <div>
                <label style={{ fontSize: "0.92rem", fontWeight: 900, color: "var(--text-main)" }}>
                  ④ 初期の投票論点（Statement）
                </label>
                <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                  参加者が最初に投票する論点（1行に1問）を入力してください。
                </div>
              </div>
              <button
                type="button"
                className="btn btn-sm btn-primary"
                disabled={suggestStmtsAct.busy || title.trim().length < 2}
                onClick={doSuggestStatements}
              >
                {suggestStmtsAct.busy ? "✨ AIが論点考案中…" : "✨ AIに初期論点を提案してもらう"}
              </button>
            </div>

            <textarea
              className="textarea"
              style={{ minHeight: "120px", fontFamily: "inherit", fontSize: "0.9rem", lineHeight: 1.6 }}
              placeholder={`1行に1つの論点を入力してください（例）：\n・利用者のプライバシー保護を最優先にした共通ルールを策定すべきだ\n・現場の業務効率化のため、ツールの導入を全面的に推奨・支援すべきだ\n・十分な合意が得られるまでは、全面的な導入は慎重に見合わせるべきだ\n\n※空欄のまま公開した場合は、AIが自動で初期論点を生成します。`}
              value={statementsText}
              onChange={(e) => setStatementsText(e.target.value)}
            />
          </div>

          {createAct.error && <div className="error-box" style={{ marginBottom: "1rem" }}>{createAct.error}</div>}

          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
            <button
              type="button"
              className="btn btn-primary"
              style={{ padding: "0.65rem 1.6rem", fontSize: "1rem", fontWeight: 900 }}
              disabled={createAct.busy || title.trim().length < 2}
              onClick={doCreate}
            >
              {createAct.busy ? "🚀 トピックを作成中…" : "🚀 このトピックを作成して公開する"}
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => setShowCreate(false)}
            >
              キャンセル
            </button>
          </div>
        </div>
      )}

      {loading && !topics && <Loading />}
      {error && <div className="error-box">{error}</div>}

      {/* Topic Card List */}
      <div style={{ display: "grid", gap: "1rem" }}>
        {topics?.map((t) => (
          <div
            key={t.id}
            className="card card-interactive"
            {...clickable(() => navigate(`/topics/${t.id}`))}
          >
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem", alignItems: "center" }}>
              <span className="badge badge-consensus">参加者 {t.n_participants}名</span>
              <span className="badge" style={{ background: "var(--bg-app)" }}>原則 {t.n_statements}件</span>
              {t.report_version && (
                <span className="badge badge-bridge">成果物 v{t.report_version} 公開中</span>
              )}
            </div>

            <h2 style={{ fontSize: "1.25rem", fontWeight: 900, margin: "0 0 0.45rem", color: "var(--text-main)", lineHeight: 1.4 }}>
              {t.title}
            </h2>

            <p style={{ margin: 0, color: "var(--text-body)", fontSize: "0.92rem", lineHeight: 1.6 }}>
              {t.description}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

type TabKey = "vote" | "list" | "post" | "map" | "diagnosis" | "report";

const TABS: { key: TabKey; icon: string; label: string; short: string }[] = [
  { key: "vote", icon: "🗳️", label: "投票する", short: "投票" },
  { key: "list", icon: "📋", label: "原則と原体験", short: "原則一覧" },
  { key: "post", icon: "✨", label: "体験から投稿", short: "声から投稿" },
  { key: "map", icon: "🗺️", label: "意見マップ", short: "意見マップ" },
  { key: "diagnosis", icon: "🎯", label: "あなたの診断", short: "診断" },
  { key: "report", icon: "📄", label: "成果物", short: "成果物" },
];

function TopicDetailPage() {
  const { id } = useParams();
  const topicId = Number(id);
  const { user } = useAuth();
  const { data: topic, loading, error, setData, reload } = useAsync(
    () => api.getTopic(topicId),
    [topicId, user?.id],
  );
  const [tab, setTab] = useState<TabKey>("vote");
  const [modalSid, setModalSid] = useState<number | null>(null);

  if (loading && !topic) return <Loading label="トピックを読み込み中…" />;
  if (error) return <div className="error-box">{error}</div>;
  if (!topic) return null;

  const tabBadge = (key: TabKey) => {
    if (key === "vote") return ` (${topic.my_progress.voted}/${topic.my_progress.total})`;
    if (key === "report" && topic.report_version) return ` v${topic.report_version}`;
    return "";
  };

  return (
    <div>
      {!user && <RegisterPanel onDone={reload} />}

      {/* Topic Hero Card */}
      <div className="card" style={{ padding: "1.5rem", marginBottom: "1rem", borderTop: "4px solid var(--brand-blue)" }}>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.45rem", alignItems: "center" }}>
          <Link to="/" style={{ fontSize: "0.86rem", fontWeight: 800 }}>
            ← トピック一覧
          </Link>
          <span className="badge badge-consensus">参加者 {topic.n_participants}名</span>
          <span className="badge" style={{ background: "var(--bg-app)" }}>原則 {topic.n_statements}件</span>
          {topic.report_version && (
            <span className="badge badge-bridge">成果物 v{topic.report_version}</span>
          )}
        </div>

        <h1 style={{ fontSize: "1.35rem", fontWeight: 900, margin: "0.2rem 0 0.45rem", color: "var(--text-main)", lineHeight: 1.4 }}>
          {topic.title}
        </h1>

        <p style={{ margin: "0 0 0.75rem", color: "var(--text-body)", fontSize: "0.92rem", lineHeight: 1.6 }}>
          {topic.description}
        </p>

        {user && (
          <div style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", background: "rgba(37,99,235,0.06)", border: "1px solid rgba(37,99,235,0.2)", borderRadius: "var(--radius-pill)", padding: "0.3rem 0.85rem", fontSize: "0.82rem", fontWeight: 700, color: "var(--brand-blue)" }}>
            <span>👤 あなた（{user.handle}）として参加中</span>
            <span>・</span>
            <span>
              {topic.my_progress.voted === topic.my_progress.total && topic.my_progress.total > 0
                ? "✓ 全問投票完了"
                : `${topic.my_progress.voted} / ${topic.my_progress.total} 問 投票済み`}
            </span>
          </div>
        )}
      </div>

      {/* Position Selector Bar */}
      {user && <PositionSelector topic={topic} onSaved={setData} />}

      {/* Desktop & Tablet Navigation Tabs */}
      <div className="tabs-nav" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            className={`tab-link ${tab === t.key ? "active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.icon} {t.label}{tabBadge(t.key)}
          </button>
        ))}
      </div>

      {/* Tab Contents */}
      {tab === "vote" && (
        <VoteTab
          topicId={topicId}
          onOpenStatement={setModalSid}
          onVoted={reload}
        />
      )}
      {tab === "list" && (
        <StatementListTab topicId={topicId} onOpenStatement={setModalSid} />
      )}
      {tab === "post" && (
        <PostTab
          topicId={topicId}
          onOpenStatement={setModalSid}
          onCreated={reload}
        />
      )}
      {tab === "map" && (
        <OpinionMapTab topicId={topicId} onOpenStatement={setModalSid} />
      )}
      {tab === "diagnosis" && (
        <DiagnosisTab topicId={topicId} onOpenStatement={setModalSid} />
      )}
      {tab === "report" && (
        <ReportTab
          topicId={topicId}
          onOpenStatement={setModalSid}
          onChanged={reload}
        />
      )}

      {/* Statement Detail Bottom Sheet / Modal */}
      {modalSid !== null && (
        <StatementModal
          statementId={modalSid}
          onClose={() => setModalSid(null)}
          onChanged={reload}
        />
      )}

      {/* Mobile Ergonomic Bottom Navigation Bar */}
      <nav className="mobile-bottom-nav">
        <div className="mobile-bottom-nav-inner">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              aria-current={tab === t.key ? "page" : undefined}
              className={`bottom-nav-item ${tab === t.key ? "active" : ""}`}
              onClick={() => {
                setTab(t.key);
                window.scrollTo({ top: 0 });
              }}
            >
              <span className="bottom-nav-item-icon">{t.icon}</span>
              <span>{t.short}</span>
            </button>
          ))}
        </div>
      </nav>
    </div>
  );
}

function ContributionsPage() {
  const { user } = useAuth();
  const { data: items, loading, error } = useAsync(
    () => (user ? api.getContributions() : Promise.resolve([])),
    [user?.id],
  );

  if (!user) {
    return (
      <div>
        <RegisterPanel />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 840, margin: "0 auto" }}>
      <div className="card" style={{ padding: "1.75rem", borderTop: "4px solid var(--brand-blue)" }}>
        <h1 style={{ fontSize: "1.35rem", fontWeight: 900, margin: "0 0 0.4rem", color: "var(--text-main)" }}>
          成果物へのあなたの貢献履歴（マクロ報酬）
        </h1>
        <p style={{ fontSize: "0.92rem", color: "var(--text-muted)", margin: 0, lineHeight: 1.6 }}>
          あなたが投じた1票や、投稿した原則・原体験が、どのトピックの成果物ドキュメント（バージョン）の形成に採用・引用されたかの透明な記録です。
        </p>
      </div>

      {loading && !items && <Loading />}
      {error && <div className="error-box">{error}</div>}

      {items && items.length === 0 && (
        <div className="card" style={{ textAlign: "center", padding: "2.5rem 1.5rem" }}>
          <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>📝</div>
          <h3 style={{ margin: "0 0 0.5rem" }}>まだ記録された貢献はありません</h3>
          <p style={{ color: "var(--text-muted)", margin: 0 }}>
            トピックで投票や原体験の投稿を行い、「成果物ドキュメント」タブで成果物が更新されるとここに記録されます。
          </p>
        </div>
      )}

      <div style={{ display: "grid", gap: "0.85rem" }}>
        {items?.map((c, idx) => (
          <div className="card" key={idx} style={{ padding: "1.25rem", borderLeft: "4px solid var(--brand-violet)" }}>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.45rem", alignItems: "center" }}>
              <span className="badge badge-bridge">{CONTRIBUTION_LABEL[c.kind]}</span>
              <span className="badge" style={{ background: "var(--bg-app)" }}>
                {c.topic_title}（成果物 v{c.report_version}）
              </span>
              <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                {formatDate(c.created_at)}
              </span>
            </div>
            <div style={{ fontWeight: 800, fontSize: "1rem", color: "var(--text-main)" }}>
              「{c.ref_text}」
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Header() {
  const { user } = useAuth();
  const location = useLocation();
  const [showProfileModal, setShowProfileModal] = useState(false);

  return (
    <>
      <header className="app-header">
        <div className="app-header-inner">
          <Link to="/" className="brand">
            <div className="brand-icon">成</div>
            <span>成果型SNS</span>
            <span className="brand-badge">Polis × 原体験</span>
          </Link>
          <nav className="nav-links">
            <Link to="/" className={`nav-item ${location.pathname === "/" ? "active" : ""}`}>
              トピック一覧
            </Link>
            <Link to="/contributions" className={`nav-item ${location.pathname === "/contributions" ? "active" : ""}`}>
              自分の貢献
            </Link>
            {user && (
              <button
                type="button"
                className="nav-user-pill"
                title="表示名・属性を変更"
                onClick={() => setShowProfileModal(true)}
              >
                <span aria-hidden="true">👤</span>
                <span className="nav-user-name">{user.handle}</span>
                <span className="nav-user-edit">✏️ 変更</span>
              </button>
            )}
          </nav>
        </div>
      </header>
      {showProfileModal && <ProfileModal onClose={() => setShowProfileModal(false)} />}
    </>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Header />
        <main className="container">
          <Routes>
            <Route path="/" element={<TopicListPage />} />
            <Route path="/topics/:id" element={<TopicDetailPage />} />
            <Route path="/contributions" element={<ContributionsPage />} />
          </Routes>
        </main>
      </BrowserRouter>
    </AuthProvider>
  );
}
