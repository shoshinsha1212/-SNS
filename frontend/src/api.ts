// API 呼び出し。参加者は端末に保存したトークンで識別する（ログインなし）。

const TOKEN_KEY = "seika.token";
const ADMIN_KEY = "seika.adminKey";

function safeGet(store: Storage, key: string): string | null {
  try {
    return store.getItem(key);
  } catch {
    return null;
  }
}
function safeSet(store: Storage, key: string, value: string | null) {
  try {
    if (value === null) store.removeItem(key);
    else store.setItem(key, value);
  } catch {
    /* 保存できない環境（プライベートモード等）では毎回新しい参加者になる */
  }
}

// テスター用の配布 URL（?t=トークン）で開かれたら、その参加者として保存し、URL からは消す
(() => {
  try {
    const url = new URL(window.location.href);
    const t = url.searchParams.get("t");
    if (!t) return;
    safeSet(localStorage, TOKEN_KEY, t);
    url.searchParams.delete("t");
    window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
  } catch {
    /* URL を読めない環境では何もしない */
  }
})();

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function raw<T>(path: string, init: RequestInit = {}, admin = false): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const tok = safeGet(localStorage, TOKEN_KEY);
  if (tok) headers.Authorization = `Bearer ${tok}`;
  if (admin) headers["X-Admin-Key"] = safeGet(sessionStorage, ADMIN_KEY) ?? "";
  const res = await fetch(path, { ...init, headers: { ...headers, ...(init.headers as object) } });
  if (!res.ok) {
    let msg = `エラーが発生しました（${res.status}）`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") msg = body.detail;
      else if (Array.isArray(body.detail) && body.detail[0]?.msg) msg = String(body.detail[0].msg).replace(/^Value error, /, "");
    } catch {
      /* 本文なし */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

let ensuring: Promise<void> | null = null;

/** 参加者トークンが無ければ作る。 */
export function ensureUser(): Promise<void> {
  if (safeGet(localStorage, TOKEN_KEY)) return Promise.resolve();
  if (!ensuring) {
    ensuring = raw<{ token: string }>("/api/users", { method: "POST" })
      .then((r) => safeSet(localStorage, TOKEN_KEY, r.token))
      .finally(() => {
        ensuring = null;
      });
  }
  return ensuring;
}

/** 参加者として呼ぶ。トークンが無効（DB が作り直された等）なら作り直して1回だけやり直す。 */
async function asUser<T>(path: string, init: RequestInit = {}): Promise<T> {
  await ensureUser();
  try {
    return await raw<T>(path, init);
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) {
      safeSet(localStorage, TOKEN_KEY, null);
      await ensureUser();
      return raw<T>(path, init);
    }
    throw e;
  }
}

const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

// ---------- 型 ----------
export type Axis = {
  key: string;
  name: string;
  left: string;
  right: string;
  left_word: string;
  right_word: string;
  description: string;
};
export type Meta = { axes: Axis[]; age_bands: string[]; map_required: number; flag_hide_threshold: number };
export type Me = {
  id: number;
  age_band: string | null;
  is_student: boolean | null;
  profile_asked: boolean;
  completed_topics: number;
  map_required: number;
};
export type TopicSummary = {
  id: number;
  title: string;
  description: string;
  origin: "seed" | "user";
  n_statements: number;
  n_participants: number;
  my_answered: number;
  completed: boolean;
};
export type StatementBrief = { id: number; body: string; origin: string; axis_key: string | null };
export type TopicDetail = {
  id: number;
  title: string;
  description: string;
  origin: string;
  statements: StatementBrief[];
  my_votes: Record<string, { value: number; reason: string | null }>;
  completed: boolean;
};
export type VoteResult = {
  value: number;
  topic_completed_now: boolean;
  completed_topics: number;
  map_completed_now: boolean;
};
export type Reason = { id: number; text: string };
export type StoryItem = { id: number; body: string; mine: boolean };
export type StatementResult = {
  id: number;
  body: string;
  axis_key: string | null;
  agree: number;
  disagree: number;
  pass: number;
  n: number;
  agree_rate: number | null;
  student_agree_rate: number | null;
  groups: { key: string; label: string; agree: number; disagree: number; pass: number }[];
  label: "few" | "consensus_agree" | "consensus_disagree" | "divided" | "leaning";
  my_vote: number | null;
  my_reason: string | null;
  same_rate: number | null;
  reasons: { agree: Reason[]; disagree: Reason[] };
  stories: { agree: StoryItem[]; disagree: StoryItem[]; other: StoryItem[] };
  n_stories: number;
};
export type Results = {
  topic: { id: number; title: string; description: string };
  n_participants: number;
  min_n: number;
  statements: StatementResult[];
  summary: {
    n_answered: number;
    n_rated: number;
    n_majority: number;
    most_minority: { id: number; body: string; same_rate: number } | null;
  };
  my_understanding: number | null;
};
export type MapAxis = Axis & {
  score: number | null;
  n_used: number;
  my_bin: number | null;
  histogram: number[];
  basis: { statement_id: number; body: string; topic_title: string; my_vote: number; toward: string }[];
};
export type ValueMap = {
  completed_topics: number;
  required: number;
  complete: boolean;
  type_name: string | null;
  code: string | null;
  axes: MapAxis[];
};
export type NewStatement = { body: string; axis_key?: string | null; direction?: 1 | -1 | null };
export type FlagTarget = "topic" | "statement" | "reason" | "story";

// ---------- 参加者 API ----------
export const api = {
  meta: () => raw<Meta>("/api/meta"),
  me: () => asUser<Me>("/api/me"),
  saveProfile: (age_band: string | null, is_student: boolean | null) =>
    asUser<Me>("/api/me", { method: "PATCH", body: JSON.stringify({ age_band, is_student }) }),
  topics: () => asUser<TopicSummary[]>("/api/topics"),
  topic: (id: number) => asUser<TopicDetail>(`/api/topics/${id}`),
  createTopic: (title: string, description: string, statements: NewStatement[]) =>
    asUser<{ id: number }>("/api/topics", post({ title, description, statements })),
  addStatement: (topicId: number, s: NewStatement) =>
    asUser<StatementBrief>(`/api/topics/${topicId}/statements`, post(s)),
  vote: (statementId: number, value: number, reason: string | null) =>
    asUser<VoteResult>(`/api/statements/${statementId}/vote`, post({ value, reason })),
  results: (id: number) => asUser<Results>(`/api/topics/${id}/results`),
  understanding: (id: number, score: number) => asUser(`/api/topics/${id}/understanding`, post({ score })),
  postStory: (statementId: number, body: string) =>
    asUser<{ id: number; body: string; stance: number }>(`/api/statements/${statementId}/stories`, post({ body })),
  flag: (target_type: FlagTarget, target_id: number) =>
    asUser<{ hidden: boolean }>("/api/flags", post({ target_type, target_id })),
  map: () => asUser<ValueMap>("/api/me/map"),
};

/** 行動計測。失敗しても画面の動作には影響させない。 */
export function track(name: string, topic_id?: number, statement_id?: number) {
  asUser("/api/events", post({ name, topic_id, statement_id })).catch(() => undefined);
}

// ---------- 管理 API ----------
export const adminKey = {
  get: () => safeGet(sessionStorage, ADMIN_KEY),
  set: (v: string | null) => safeSet(sessionStorage, ADMIN_KEY, v),
};
export type Metrics = {
  funnel: { key: string; label: string; users: number; raw: number }[];
  return_7d: { visitors: number; returned: number };
  understanding: { avg: number | null; n: number; dist: number[] };
  content: Record<string, number>;
  daily: { date: string; visits: number; votes: number }[];
  topics: {
    id: number;
    title: string;
    origin: string;
    hidden: boolean;
    n_statements: number;
    viewers: number;
    voters: number;
    completers: number;
    dropoff: { answered: number; users: number }[];
    understanding_avg: number | null;
    understanding_n: number;
  }[];
};
export type FlagRow = { target_type: FlagTarget; target_id: number; count: number; text: string; hidden: boolean; last_at: string };
export type AdminStatement = {
  id: number;
  topic_id: number;
  topic_title: string;
  body: string;
  origin: string;
  axis_key: string | null;
  direction: number | null;
  hidden: boolean;
};
export const adminApi = {
  metrics: () => raw<Metrics>("/api/admin/metrics", {}, true),
  flags: () => raw<FlagRow[]>("/api/admin/flags", {}, true),
  moderate: (target_type: FlagTarget, target_id: number, action: "hide" | "show" | "delete") =>
    raw("/api/admin/moderate", post({ target_type, target_id, action }), true),
  statements: () => raw<AdminStatement[]>("/api/admin/statements", {}, true),
  tag: (id: number, axis_key: string | null, direction: number | null) =>
    raw(`/api/admin/statements/${id}`, { method: "PATCH", body: JSON.stringify({ axis_key, direction }) }, true),
};
