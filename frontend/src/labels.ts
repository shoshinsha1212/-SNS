import type { ContributionKind, Origin, Section, Stance, StoryKind } from "./api";

export const SECTION_LABEL: Record<Section, string> = {
  consensus: "立場を越えた共通原則",
  divergence: "立場によって見え方が違う論点",
  bridge: "条件付き合意案",
  value_split: "立場によらず割れている論点",
  undecided: "データ不足",
};

export const SECTION_DESC: Record<Section, string> = {
  consensus: "どの立場の人たちからも、多くの賛成が集まっている原則です。",
  divergence:
    "立場によって賛否が大きく分かれている論点です。利害の違いか、その立場でしか得られない経験の違いかは数字だけではわかりません。体験談を読んで考えてみてください。",
  bridge: "立場の違いを踏まえた条件つきの案で、どの立場からも一定の賛成を得ています。",
  value_split: "賛否は割れていますが、立場では説明できない論点です。個人の価値観の違いが表れているのかもしれません。",
  undecided: "まだ投票が少なく、判断できるだけのデータがありません。",
};

export const SECTION_ORDER: Section[] = ["consensus", "divergence", "bridge", "value_split", "undecided"];

export const ORIGIN_LABEL: Record<Origin, string | null> = {
  seed: null,
  user: "参加者の投稿",
  ai_from_complaint: "声から生まれた原則",
  ai_bridge: "AIの条件付き合意案",
};

export const STORY_KIND_LABEL: Record<StoryKind, string> = {
  past: "過去の体験",
  present: "現在の現実",
  future: "未来のシナリオ",
};

export const STANCE_LABEL: Record<Stance, string> = {
  supports: "賛成側の体験談",
  opposes: "反対側の体験談",
  context: "背景・状況",
};

export const STANCE_SHORT: Record<Stance, string> = {
  supports: "賛成側",
  opposes: "反対側",
  context: "背景",
};

export const CONTRIBUTION_LABEL: Record<ContributionKind, string> = {
  vote: "投票",
  decisive_vote: "後押しした一票",
  statement_adopted: "原則の採用",
  story_cited: "体験談の引用",
};

export function pct(rate: number | null | undefined): string {
  if (rate === null || rate === undefined || Number.isNaN(rate)) return "—";
  return `${Math.round(rate * 100)}%`;
}

/** gap は 0〜1 の賛成率差を想定。1 を超えていればすでにポイント表記とみなす。 */
export function gapPoints(gap: number | null | undefined): number | null {
  if (gap === null || gap === undefined) return null;
  return Math.round(gap > 1 ? gap : gap * 100);
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ja-JP", { year: "numeric", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** 立場間ギャップを中立的な言葉にする（PD などの生値は出さない） */
export function gapWords(gap: number | null | undefined): string | null {
  const p = gapPoints(gap);
  if (p === null) return null;
  if (p >= 30) return "立場によって見え方が大きく違う";
  if (p >= 15) return "立場によって見え方がやや違う";
  return "立場による違いは小さい";
}
