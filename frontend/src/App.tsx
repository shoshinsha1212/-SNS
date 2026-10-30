import { useState } from "react";
import { BrowserRouter, Link, Route, Routes, useNavigate, useParams, useLocation } from "react-router-dom";
import { api, type SuggestedAxis } from "./api";
import { AuthProvider, useAuth } from "./auth";
import { StatementModal } from "./components/Common";
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

function RegisterPanel({ onDone }: { onDone?: () => void }) {
  const { login } = useAuth();
  const { data: meta } = useAsync(() => api.getMeta(), []);
  const [handle, setHandle] = useState("ゲスト参加者");
  const [attrs, setAttrs] = useState<Record<string, string>>({});
  const { busy, error, exec } = useAction();

  const submit = () =>
    exec(async () => {
      const res = await api.createUser(handle.trim() || "匿名参加者", attrs);
      login(res.user, res.token);
      onDone?.();
    });

  return (
    <div className="card" style={{ borderLeft: "4px solid var(--brand-blue)", background: "#ffffff" }}>
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
  const { user } = useAuth();
  const navigate = useNavigate();
  const { data: topics, loading, error, reload } = useAsync(() => api.listTopics(), []);
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [axes, setAxes] = useState<SuggestedAxis[]>([]);
  const suggestAct = useAction();
  const createAct = useAction();

  const doSuggest = () =>
    suggestAct.exec(async () => {
      const res = await api.suggestAxes(title, desc);
      setAxes(res.axes);
    });

  const doCreate = () =>
    createAct.exec(async () => {
      const created = await api.createTopic(
        title,
        desc,
        axes.map((a) => ({ name: a.name, options: a.options })),
      );
      setShowCreate(false);
      reload();
      navigate(`/topics/${created.id}`);
    });

  return (
    <div>
      {!user && <RegisterPanel />}

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

      {/* Actions bar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem", flexWrap: "wrap", gap: "0.75rem" }}>
        <div>
          <h2 style={{ fontSize: "1.25rem", fontWeight: 900, margin: 0, color: "var(--text-main)" }}>
            議論トピック一覧
          </h2>
        </div>
        {user && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => setShowCreate((s) => !s)}
          >
            {showCreate ? "✕ フォームを閉じる" : "＋ 新しいトピックを立てる"}
          </button>
        )}
      </div>

      {/* Create Topic Modal / Box */}
      {showCreate && (
        <div className="card" style={{ padding: "1.75rem", borderLeft: "4px solid var(--bridge-gradient)" }}>
          <h3 style={{ marginTop: 0, fontSize: "1.15rem", fontWeight: 800 }}>新しい議論トピックを作成</h3>
          <div style={{ marginBottom: "0.85rem" }}>
            <label style={{ fontSize: "0.88rem", fontWeight: 800, display: "block", marginBottom: "0.3rem" }}>
              トピックのタイトル
            </label>
            <input
              className="input"
              placeholder="例：クリエイティブ制作と生成AIの学習データ還元ルール"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>

          <div style={{ marginBottom: "0.85rem" }}>
            <label style={{ fontSize: "0.88rem", fontWeight: 800, display: "block", marginBottom: "0.3rem" }}>
              説明・問いかけ
            </label>
            <textarea
              className="textarea"
              placeholder="このトピックで参加者からどのような原則や原体験を集めたいかを記述してください"
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
            />
          </div>

          <div style={{ marginBottom: "1rem" }}>
            <button
              type="button"
              className="btn btn-sm"
              disabled={suggestAct.busy || title.trim().length < 2}
              onClick={doSuggest}
            >
              {suggestAct.busy ? "分析・提案中…" : "✨ AIに「立場の軸」を提案してもらう"}
            </button>
          </div>

          {axes.length > 0 && (
            <div className="card-subtle" style={{ marginBottom: "1rem" }}>
              <div style={{ fontWeight: 800, fontSize: "0.92rem", color: "var(--text-main)", marginBottom: "0.5rem" }}>
                設定された立場の軸（必要に応じて選択肢を編集してください）
              </div>
              {axes.map((ax, idx) => (
                <div key={idx} style={{ marginBottom: "0.75rem" }}>
                  <input
                    className="input"
                    style={{ marginBottom: "0.35rem", fontWeight: 700 }}
                    value={ax.name}
                    onChange={(e) => {
                      const copy = [...axes];
                      copy[idx] = { ...ax, name: e.target.value };
                      setAxes(copy);
                    }}
                  />
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
                  />
                  <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
                    理由：{ax.why_divergent}
                  </div>
                </div>
              ))}
            </div>
          )}

          {createAct.error && <div className="error-box">{createAct.error}</div>}

          <button
            type="button"
            className="btn btn-primary"
            disabled={createAct.busy || title.trim().length < 2}
            onClick={doCreate}
          >
            このトピックを公開する
          </button>
        </div>
      )}

      {loading && <div className="card" style={{ textAlign: "center" }}>読み込み中…</div>}
      {error && <div className="error-box">{error}</div>}

      {/* Topic Card List */}
      <div style={{ display: "grid", gap: "1rem" }}>
        {topics?.map((t) => (
          <div
            key={t.id}
            className="card card-interactive"
            onClick={() => navigate(`/topics/${t.id}`)}
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

  if (loading && !topic) return <div className="card" style={{ textAlign: "center" }}>読み込み中…</div>;
  if (error) return <div className="error-box">{error}</div>;
  if (!topic) return null;

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

        <p style={{ margin: 0, color: "var(--text-body)", fontSize: "0.92rem", lineHeight: 1.6 }}>
          {topic.description}
        </p>
      </div>

      {/* Position Selector Bar */}
      {user && <PositionSelector topic={topic} onSaved={setData} />}

      {/* Desktop & Tablet Navigation Tabs */}
      <div className="tabs-nav">
        <button
          type="button"
          className={`tab-link ${tab === "vote" ? "active" : ""}`}
          onClick={() => setTab("vote")}
        >
          🗳️ 1. 投票する ({topic.my_progress.voted}/{topic.my_progress.total})
        </button>
        <button
          type="button"
          className={`tab-link ${tab === "list" ? "active" : ""}`}
          onClick={() => setTab("list")}
        >
          📋 2. 原則と原体験一覧
        </button>
        <button
          type="button"
          className={`tab-link ${tab === "post" ? "active" : ""}`}
          onClick={() => setTab("post")}
        >
          ✨ 3. 不満・体験から投稿
        </button>
        <button
          type="button"
          className={`tab-link ${tab === "map" ? "active" : ""}`}
          onClick={() => setTab("map")}
        >
          🗺️ 4. 意見マップ・立場のレンズ
        </button>
        <button
          type="button"
          className={`tab-link ${tab === "diagnosis" ? "active" : ""}`}
          onClick={() => setTab("diagnosis")}
        >
          🎯 5. あなたの診断
        </button>
        <button
          type="button"
          className={`tab-link ${tab === "report" ? "active" : ""}`}
          onClick={() => setTab("report")}
        >
          📄 6. 成果物ドキュメント {topic.report_version ? `(v${topic.report_version})` : ""}
        </button>
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
          <button
            type="button"
            className={`bottom-nav-item ${tab === "vote" ? "active" : ""}`}
            onClick={() => setTab("vote")}
          >
            <span className="bottom-nav-item-icon">🗳️</span>
            <span>投票</span>
          </button>
          <button
            type="button"
            className={`bottom-nav-item ${tab === "list" ? "active" : ""}`}
            onClick={() => setTab("list")}
          >
            <span className="bottom-nav-item-icon">📋</span>
            <span>原則一覧</span>
          </button>
          <button
            type="button"
            className={`bottom-nav-item ${tab === "post" ? "active" : ""}`}
            onClick={() => setTab("post")}
          >
            <span className="bottom-nav-item-icon">✨</span>
            <span>声から投稿</span>
          </button>
          <button
            type="button"
            className={`bottom-nav-item ${tab === "map" ? "active" : ""}`}
            onClick={() => setTab("map")}
          >
            <span className="bottom-nav-item-icon">🗺️</span>
            <span>意見マップ</span>
          </button>
          <button
            type="button"
            className={`bottom-nav-item ${tab === "diagnosis" ? "active" : ""}`}
            onClick={() => setTab("diagnosis")}
          >
            <span className="bottom-nav-item-icon">🎯</span>
            <span>診断</span>
          </button>
          <button
            type="button"
            className={`bottom-nav-item ${tab === "report" ? "active" : ""}`}
            onClick={() => setTab("report")}
          >
            <span className="bottom-nav-item-icon">📄</span>
            <span>成果物</span>
          </button>
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

      {loading && <div className="card" style={{ textAlign: "center" }}>読み込み中…</div>}
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
  const { user, logout } = useAuth();
  const location = useLocation();

  return (
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
          {user ? (
            <div className="nav-user-pill">
              <span>👤 {user.handle}</span>
              <button
                type="button"
                className="btn btn-sm"
                style={{ padding: "0.15rem 0.5rem", fontSize: "0.76rem" }}
                onClick={logout}
              >
                切替
              </button>
            </div>
          ) : (
            <span className="badge">未登録</span>
          )}
        </nav>
      </div>
    </header>
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
