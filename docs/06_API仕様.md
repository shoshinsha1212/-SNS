# 06 API仕様（MVP）

バックエンド（FastAPI, `backend/`）とフロントエンド（React + Vite, `frontend/`）の取り決めです。

- ベースURL：`/api`（開発時は Vite のプロキシで `http://localhost:8000` に転送）
- 認証：`POST /api/users` で得たトークンを `Authorization: Bearer <token>` で送る（MVPでは簡易認証）
- IDはすべて整数
- 立場の「次元（dimension）」は文字列キーで表す：トピック固有の軸は `axis:<axis_id>`、基本属性は `attr:<key>`（例 `attr:age_band`）
- 人数が10人未満のグループの賛成率は `hidden: true`、`agree_rate: null` で返す（[04](./04_プライバシーと不正対策.md) の最小人数ルール）

## 共通の型

```ts
type User = { id: number; handle: string; attributes: Record<string, string> };

type TopicSummary = {
  id: number; title: string; description: string; status: "open" | "closed";
  n_participants: number; n_statements: number; report_version: string | null;
};

type Axis = { id: number; name: string; options: { id: number; label: string }[] };

type StatementBrief = {
  id: number; text: string;
  origin: "seed" | "user" | "ai_from_complaint" | "ai_bridge";
  author_is_me: boolean; n_stories: number;
};

type PositionRate = {
  dimension: string; dimension_label: string;
  group: string; group_label: string;
  n: number;                    // 賛成+反対の人数
  agree_rate: number | null;    // 平滑化した賛成率（hidden のとき null）
  hidden: boolean;
};

type StoryCard = {
  id: number; kind: "past" | "present" | "future";
  summary: string; body: string;
  stance: "supports" | "opposes" | "context";
  author_position_label: string | null;  // 例「教員」
  is_boundary: boolean;                    // 立場を越えた体験
  is_mine: boolean;
  reactions: { resonate: number; understand: number };
  my_reactions: ("resonate" | "understand")[];
};

type Section = "consensus" | "divergence" | "bridge" | "value_split" | "undecided";
```

## エンドポイント

### ユーザー・メタ情報
| メソッド | パス | 入力 | 出力 |
|---|---|---|---|
| GET | `/api/meta` | | `{ attributes: {key,label,options:string[]}[] }`（基本属性の選択肢） |
| POST | `/api/users` | `{ handle, attributes }` | `{ user: User, token }` |
| GET | `/api/me` | | `User` |
| GET | `/api/me/contributions` | | `{ topic_id, topic_title, report_version, kind, ref_type, ref_id, ref_text, weight, created_at }[]` |

`kind`：`vote` / `decisive_vote` / `statement_adopted` / `story_cited`

### トピック
| メソッド | パス | 入力 | 出力 |
|---|---|---|---|
| GET | `/api/topics` | | `TopicSummary[]` |
| POST | `/api/topics/suggest-axes` | `{ title, description }` | `{ axes: {name, options: string[], why_divergent}[], ai: "llm"\|"mock" }` |
| POST | `/api/topics` | `{ title, description, axes: {name, options: string[]}[] }` | `TopicDetail` |
| GET | `/api/topics/{id}` | | `TopicDetail` |
| PUT | `/api/topics/{id}/positions` | `{ positions: Record<axis_id, option_id> }` | `TopicDetail` |
| POST | `/api/topics/{id}/analyze` | | `{ snapshot_id, report_version: string\|null }` |

```ts
type TopicDetail = TopicSummary & {
  axes: Axis[];
  my_positions: Record<string, number>;      // axis_id -> option_id
  my_progress: { voted: number; total: number };
  analysis: { last_computed_at: string | null; votes_since: number };
};
```

### 原則と投票
| メソッド | パス | 入力 | 出力 |
|---|---|---|---|
| GET | `/api/topics/{id}/next-statement` | | `{ statement: StatementBrief \| null, progress: {voted,total} }` |
| GET | `/api/topics/{id}/statements` | | `(StatementBrief & { my_vote: 1\|-1\|0\|null, counts:{agree,disagree,pass}, section: Section\|null, gap: number\|null })[]` |
| POST | `/api/topics/{id}/convert` | `{ text }` | P1：`{ principles: {text,type}[], story_draft: {kind,text}\|null, needs_clarification, clarifying_question, ai }` |
| POST | `/api/topics/{id}/statements` | `{ text, origin?: "user"\|"ai_from_complaint", story?: {kind, body} }` | `{ statement: StatementBrief\|null, merged_into: {id,text}\|null, rejected_reason: string\|null }` |
| GET | `/api/statements/{id}` | | `StatementDetail` |
| POST | `/api/statements/{id}/vote` | `{ value: 1\|-1\|0 }` | `{ my_vote, counts, by_position: PositionRate[] }` |
| POST | `/api/statements/{id}/bridges` | | P5：`{ concerns: {support_side, oppose_side}\|null, created: StatementBrief[], ai, message: string\|null }` |

```ts
type StatementDetail = StatementBrief & {
  status: string; my_vote: 1 | -1 | 0 | null;
  counts: { agree: number; disagree: number; pass: number };
  stats: null | {                     // 最新の分析結果（未分析なら null）
    section: Section; pd: number | null; pd_by_dimension: Record<string, number>;
    gap: number | null; gap_dimension: string | null; gap_dimension_label: string | null;
    q_value: number | null; gic: number | null;
  };
  by_position: PositionRate[];        // 現在の票からの即時集計
  stories: { supports: StoryCard[]; opposes: StoryCard[]; context: StoryCard[] };
};
```

### 原体験
| メソッド | パス | 入力 | 出力 |
|---|---|---|---|
| POST | `/api/stories/anonymize` | `{ body }` | P4：`{ masked_body, summary, masked_items: string[], ai }` |
| POST | `/api/statements/{id}/stories` | `{ kind, body, summary?, stance }` | `StoryCard` |
| POST | `/api/stories/{id}/reactions` | `{ kind: "resonate"\|"understand" }`（押すたびに切り替え） | `{ reactions, my_reactions }` |

### 分析結果
| メソッド | パス | 出力 |
|---|---|---|
| GET | `/api/topics/{id}/map` | `MapData` |
| GET | `/api/topics/{id}/diagnosis` | `Diagnosis` |
| GET | `/api/topics/{id}/reports` | `{ version, created_at, generator }[]`（新しい順） |
| GET | `/api/topics/{id}/report` | 最新の `Report`（なければ 404） |
| GET | `/api/topics/{id}/reports/{version}` | `Report` |

```ts
type MapData = {
  available: boolean; reason: string | null;
  snapshot_id: number | null; computed_at: string | null;
  points: { x: number; y: number; cluster: number; is_me: boolean;
            groups: Record<string, string> }[];   // dimension -> group_label（10人未満は「その他」）
  clusters: { id: number; size: number; cx: number; cy: number;
              top_statements: { id: number; text: string; agree_rate: number }[] }[];
  dimensions: { key: string; label: string }[];
  topic_dependency: { dimension: string; label: string; nmi: number }[];
};

type Diagnosis = {
  ready: boolean; needed: number;          // 診断に必要な残りの投票数
  cluster: number | null;
  typicality: null | { score: number; matched: number; total: number;
                       dimension_label: string; group_label: string };
  distinctive: { statement_id: number; text: string; my_vote: 1 | -1;
                 group_label: string; group_vote_rate: number }[];
  stories: { same: StoryCard | null; other: StoryCard | null };
};

type Report = {
  version: string; created_at: string; generator: "llm" | "template";
  body_md: string;      // 本文中の引用は [S:12]（原則）・[T:5]（体験談）の形
  sections: Record<Section, number[]>;
  params: Record<string, number>;
  n_participants: number;
};
```
