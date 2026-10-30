// APIクライアント（docs/06_API仕様.md に準拠）
// 型は仕様書の定義をそのまま TypeScript 化している。

// ---------- 共通の型 ----------
export type User = { id: number; handle: string; attributes: Record<string, string> };

export type TopicSummary = {
  id: number;
  title: string;
  description: string;
  status: "open" | "closed";
  n_participants: number;
  n_statements: number;
  report_version: string | null;
};

export type Axis = { id: number; name: string; options: { id: number; label: string }[] };

export type Origin = "seed" | "user" | "ai_from_complaint" | "ai_bridge";

export type StatementBrief = {
  id: number;
  text: string;
  origin: Origin;
  author_is_me: boolean;
  n_stories: number;
};

export type PositionRate = {
  dimension: string;
  dimension_label: string;
  group: string;
  group_label: string;
  n: number; // 賛成+反対の人数
  agree_rate: number | null; // 平滑化した賛成率（hidden のとき null）
  hidden: boolean;
};

export type StoryKind = "past" | "present" | "future";
export type Stance = "supports" | "opposes" | "context";
export type ReactionKind = "resonate" | "understand";

export type StoryCard = {
  id: number;
  kind: StoryKind;
  summary: string;
  body: string;
  stance: Stance;
  author_position_label: string | null;
  is_boundary: boolean;
  is_mine: boolean;
  reactions: { resonate: number; understand: number };
  my_reactions: ReactionKind[];
};

export type Section = "consensus" | "divergence" | "bridge" | "value_split" | "undecided";

export type VoteValue = 1 | -1 | 0;
export type Counts = { agree: number; disagree: number; pass: number };

// ---------- ユーザー・メタ ----------
export type MetaAttribute = { key: string; label: string; options: string[] };
export type Meta = { attributes: MetaAttribute[] };

export type ContributionKind = "vote" | "decisive_vote" | "statement_adopted" | "story_cited";
export type Contribution = {
  topic_id: number;
  topic_title: string;
  report_version: string | null;
  kind: ContributionKind;
  ref_type: string;
  ref_id: number;
  ref_text: string;
  weight: number;
  created_at: string;
};

// ---------- トピック ----------
export type AiKind = "llm" | "mock";

export type SuggestedAxis = { name: string; options: string[]; why_divergent: string };
export type SuggestAxesResponse = { axes: SuggestedAxis[]; ai: AiKind };

export type TopicDetail = TopicSummary & {
  axes: Axis[];
  my_positions: Record<string, number>; // axis_id -> option_id
  my_progress: { voted: number; total: number };
  analysis: { last_computed_at: string | null; votes_since: number };
};

export type Progress = { voted: number; total: number };

// ---------- 原則と投票 ----------
export type StatementListItem = StatementBrief & {
  my_vote: VoteValue | null;
  counts: Counts;
  section: Section | null;
  gap: number | null;
};

export type ConvertResponse = {
  principles: { text: string; type: string }[];
  story_draft: { kind: StoryKind; text: string } | null;
  needs_clarification: boolean;
  clarifying_question: string | null;
  ai: AiKind;
};

export type PostStatementResponse = {
  statement: StatementBrief | null;
  merged_into: { id: number; text: string } | null;
  rejected_reason: string | null;
};

export type StatementStats = {
  section: Section;
  pd: number | null;
  pd_by_dimension: Record<string, number>;
  gap: number | null;
  gap_dimension: string | null;
  gap_dimension_label: string | null;
  q_value: number | null;
  gic: number | null;
};

export type StatementDetail = StatementBrief & {
  status: string;
  my_vote: VoteValue | null;
  counts: Counts;
  stats: StatementStats | null;
  by_position: PositionRate[];
  stories: { supports: StoryCard[]; opposes: StoryCard[]; context: StoryCard[] };
};

export type VoteResponse = { my_vote: VoteValue; counts: Counts; by_position: PositionRate[] };

export type BridgesResponse = {
  concerns: { support_side: string; oppose_side: string } | null;
  created: StatementBrief[];
  ai: AiKind;
  message: string | null;
};

// ---------- 原体験 ----------
export type AnonymizeResponse = {
  masked_body: string;
  summary: string;
  masked_items: string[];
  ai: AiKind;
};

// ---------- 分析結果 ----------
export type MapData = {
  available: boolean;
  reason: string | null;
  snapshot_id: number | null;
  computed_at: string | null;
  points: { x: number; y: number; cluster: number; is_me: boolean; groups: Record<string, string> }[];
  clusters: {
    id: number;
    size: number;
    cx: number;
    cy: number;
    top_statements: { id: number; text: string; agree_rate: number }[];
  }[];
  dimensions: { key: string; label: string }[];
  topic_dependency: { dimension: string; label: string; nmi: number }[];
};

export type Diagnosis = {
  ready: boolean;
  needed: number;
  cluster: number | null;
  typicality: null | {
    score: number;
    matched: number;
    total: number;
    dimension_label: string;
    group_label: string;
  };
  distinctive: {
    statement_id: number;
    text: string;
    my_vote: 1 | -1;
    group_label: string;
    group_vote_rate: number;
  }[];
  stories: { same: StoryCard | null; other: StoryCard | null };
};

export type ReportMeta = { version: string; created_at: string; generator: "llm" | "template" };

export type Report = {
  version: string;
  created_at: string;
  generator: "llm" | "template";
  body_md: string;
  sections: Record<Section, number[]>;
  params: Record<string, number>;
  n_participants: number;
};

// ---------- 通信の土台 ----------
const TOKEN_KEY = "seika_sns_token";
const DEVICE_KEY = "seika_sns_device_id";

export function getDeviceId(): string {
  let devId = localStorage.getItem(DEVICE_KEY);
  if (!devId) {
    devId =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `dev_${Date.now()}_${Math.random().toString(36).substring(2, 10)}`;
    localStorage.setItem(DEVICE_KEY, devId);
  }
  return devId;
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number; // 0 = 通信できなかった
  detail: string | null;
  constructor(status: number, message: string, detail: string | null = null) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

function friendlyMessage(status: number, detail: string | null): string {
  if (status === 0) {
    return "サーバーに接続できませんでした。バックエンド（http://localhost:8000）が起動しているか確認してください。";
  }
  if (status === 401) return "ログイン情報が見つからないか、期限切れです。はじめにページから登録し直してください。";
  if (status === 403) return "この操作を行う権限がありません。";
  if (status === 404) return detail ?? "データが見つかりませんでした。";
  if (status === 422) return detail ? `入力内容を確認してください：${detail}` : "入力内容を確認してください。";
  if (status === 429) return "操作が集中しています。少し時間をおいてお試しください。";
  if (status >= 500) {
    return detail
      ? `サーバーでエラーが発生しました：${detail}`
      : "サーバーでエラーが発生しました。しばらくしてからもう一度お試しください。";
  }
  return detail ?? `エラーが発生しました（${status}）。`;
}

function extractDetail(body: unknown): string | null {
  if (!body || typeof body !== "object") return null;
  const d = (body as { detail?: unknown }).detail;
  if (typeof d === "string") return d;
  // FastAPI の検証エラー形式 [{loc, msg, type}]
  if (Array.isArray(d)) {
    return d
      .map((e) => (e && typeof e === "object" && "msg" in e ? String((e as { msg: unknown }).msg) : String(e)))
      .join(" / ");
  }
  return null;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, friendlyMessage(0, null));
  }

  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!res.ok) {
    // Vite のプロキシは接続失敗時に 502/504 などを返し、本文が JSON でない
    if ((res.status === 502 || res.status === 503 || res.status === 504) && data === null) {
      throw new ApiError(0, friendlyMessage(0, null));
    }
    const detail = extractDetail(data);
    throw new ApiError(res.status, friendlyMessage(res.status, detail), detail);
  }
  if (data === null && text) {
    throw new ApiError(res.status, "サーバーの応答を読み取れませんでした（JSON ではありません）。");
  }
  return data as T;
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return "不明なエラーが発生しました。";
}

// ---------- エンドポイント ----------
export const api = {
  // ユーザー・メタ
  getMeta: () => request<Meta>("GET", "/meta"),
  createUser: (handle: string, attributes: Record<string, string>, deviceId?: string) =>
    request<{ user: User; token: string }>("POST", "/users", {
      handle,
      attributes,
      device_id: deviceId ?? getDeviceId(),
    }),
  updateMe: (handle: string, attributes: Record<string, string>) =>
    request<User>("PUT", "/me", { handle, attributes }),
  getMe: () => request<User>("GET", "/me"),
  getContributions: () => request<Contribution[]>("GET", "/me/contributions"),

  // トピック
  listTopics: () => request<TopicSummary[]>("GET", "/topics"),
  suggestAxes: (title: string, description: string) =>
    request<SuggestAxesResponse>("POST", "/topics/suggest-axes", { title, description }),
  suggestStatements: (title: string, description: string) =>
    request<{ statements: string[] }>("POST", "/topics/suggest-statements", { title, description }),
  createTopic: (
    title: string,
    description: string,
    axes: { name: string; options: string[] }[],
    initialStatements?: string[],
  ) =>
    request<TopicDetail>("POST", "/topics", {
      title,
      description,
      axes,
      initial_statements: initialStatements ?? [],
    }),
  getTopic: (id: number) => request<TopicDetail>("GET", `/topics/${id}`),
  putPositions: (id: number, positions: Record<string, number>) =>
    request<TopicDetail>("PUT", `/topics/${id}/positions`, { positions }),
  analyze: (id: number) =>
    request<{ snapshot_id: number; report_version: string | null }>("POST", `/topics/${id}/analyze`),

  // 原則と投票
  nextStatement: (topicId: number) =>
    request<{ statement: StatementBrief | null; progress: Progress }>("GET", `/topics/${topicId}/next-statement`),
  listStatements: (topicId: number) => request<StatementListItem[]>("GET", `/topics/${topicId}/statements`),
  convert: (topicId: number, text: string) => request<ConvertResponse>("POST", `/topics/${topicId}/convert`, { text }),
  postStatement: (
    topicId: number,
    payload: { text: string; origin?: "user" | "ai_from_complaint"; story?: { kind: StoryKind; body: string } },
  ) => request<PostStatementResponse>("POST", `/topics/${topicId}/statements`, payload),
  getStatement: (id: number) => request<StatementDetail>("GET", `/statements/${id}`),
  vote: (id: number, value: VoteValue) => request<VoteResponse>("POST", `/statements/${id}/vote`, { value }),
  bridges: (id: number) => request<BridgesResponse>("POST", `/statements/${id}/bridges`),

  // 原体験
  anonymize: (body: string) => request<AnonymizeResponse>("POST", "/stories/anonymize", { body }),
  postStory: (statementId: number, payload: { kind: StoryKind; body: string; summary?: string; stance: Stance }) =>
    request<StoryCard>("POST", `/statements/${statementId}/stories`, payload),
  react: (storyId: number, kind: ReactionKind) =>
    request<{ reactions: StoryCard["reactions"]; my_reactions: ReactionKind[] }>(
      "POST",
      `/stories/${storyId}/reactions`,
      { kind },
    ),

  // 分析結果
  getMap: (topicId: number) => request<MapData>("GET", `/topics/${topicId}/map`),
  getDiagnosis: (topicId: number) => request<Diagnosis>("GET", `/topics/${topicId}/diagnosis`),
  listReports: (topicId: number) => request<ReportMeta[]>("GET", `/topics/${topicId}/reports`),
  getLatestReport: (topicId: number) => request<Report>("GET", `/topics/${topicId}/report`),
  getReport: (topicId: number, version: string) =>
    request<Report>("GET", `/topics/${topicId}/reports/${encodeURIComponent(version)}`),
};
