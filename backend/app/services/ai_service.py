"""AIパイプライン（docs/03_AIパイプライン.md の実装）。

環境変数 OPENAI_API_KEY が設定されていれば OpenAI 互換 API を呼び出し、
未設定または通信不可の場合はルール・テンプレートによる決定論的フォールバック（"mock" / "template"）で動作する。
"""

from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher
from typing import Any

import httpx

MODERATION_NG_WORDS = [
    "死ね",
    "殺す",
    "バカ",
    "アホ",
    "消えろ",
    "無能",
]


def _call_llm_json(prompt: str) -> dict[str, Any] | None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    try:
        resp = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "temperature": 0.3,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception:
        return None


# ---------- P7 規約チェック ----------
def check_moderation(text: str) -> str | None:
    """規約違反があれば理由を返し、問題なければ None を返す。"""
    cleaned = text.strip()
    if len(cleaned) < 4:
        return "文字数が短すぎます（4文字以上で入力してください）。"
    for w in MODERATION_NG_WORDS:
        if w in cleaned:
            return f"攻撃的な表現（{w}）が含まれているため投稿できません。論点や背景の記述に言い換えてください。"
    return None


# ---------- P1 不満・体験 → 原則の変換 ----------
def convert_complaint(topic_title: str, topic_desc: str, text: str) -> dict[str, Any]:
    raw = text.strip()
    if len(raw) < 6:
        return {
            "principles": [],
            "story_draft": None,
            "needs_clarification": True,
            "clarifying_question": "どのような場面で困ったか、またはどうなってほしいかをもう少し具体的に教えてください。",
            "ai": "mock",
        }

    prompt = (
        f"あなたは市民の声を「投票できる原則」に整える編集者です。\n"
        f"# トピック\n{topic_title}：{topic_desc}\n"
        f"# 参加者の投稿\n{raw}\n"
        f"JSON形式で principles: [{{text, type}}], story_draft: {{kind, text}}|null, "
        f"needs_clarification: bool, clarifying_question: str|null を出力してください。"
    )
    llm_res = _call_llm_json(prompt)
    if llm_res and isinstance(llm_res.get("principles"), list):
        return {
            "principles": llm_res.get("principles", [])[:3],
            "story_draft": llm_res.get("story_draft"),
            "needs_clarification": bool(llm_res.get("needs_clarification", False)),
            "clarifying_question": llm_res.get("clarifying_question"),
            "ai": "llm",
        }

    # ルールベースの変換フォールバック
    sentences = [s.strip() for s in re.split(r"[。！？\n]+", raw) if s.strip()]
    principles: list[dict[str, str]] = []
    story_sentences: list[str] = []

    for s in sentences:
        if any(s.endswith(suf) for suf in ("べきだ", "べきである", "してほしい", "してはならない", "べきではない")):
            p_type = "should_not" if ("ならない" in s or "ではない" in s) else ("want" if "ほしい" in s else "should")
            principles.append({"text": s[:80], "type": p_type})
        elif any(k in s for k in ("困る", "不安", "怖い", "おかしい", "不満", "やめて", "危険", "負担")):
            core = re.sub(r"(のが困る|のが不安|で困っている|のが怖い|はおかしい|で負担だ).*$", "", s)
            core = core[:55]
            principles.append({"text": f"{core}に対する明確な歯止めと対策を設けるべきだ", "type": "should"})
            story_sentences.append(s)
        elif any(k in s for k in ("必要", "大事", "大切", "認め", "活用", "推進")):
            core = s[:60]
            principles.append({"text": f"{core}ための環境とルールを整えるべきだ", "type": "should"})
        else:
            story_sentences.append(s)

    if not principles:
        summary_head = raw[:50].rstrip("、。")
        principles.append(
            {
                "text": f"「{summary_head}」のような現場の課題に対応できる運用ルールを設けるべきだ",
                "type": "should",
            }
        )
        story_sentences = sentences

    kind = "present"
    if any(w in raw for w in ("以前", "昔", "去年", "だった", "したとき", "経験")):
        kind = "past"
    elif any(w in raw for w in ("将来", "今後", "未来", "このままでは", "なるだろう", "懸念")):
        kind = "future"

    story_draft = None
    if story_sentences or len(raw) >= 25:
        story_draft = {"kind": kind, "text": anonymize_story(raw)["masked_body"]}

    return {
        "principles": principles[:3],
        "story_draft": story_draft,
        "needs_clarification": False,
        "clarifying_question": None,
        "ai": "mock",
    }


# ---------- P2 重複の判定 ----------
def _char_ngrams(text: str, n: int = 2) -> set[str]:
    s = re.sub(r"\s+", "", text)
    if len(s) < n:
        return {s}
    return {s[i : i + n] for i in range(len(s) - n + 1)}


def check_duplicate(new_text: str, existing: list[tuple[int, str]]) -> tuple[int, str] | None:
    """実質的に同じ既存の原則があれば (id, text) を返す。条件や強さの違いは別物として残す。"""
    norm_new = re.sub(r"[。、\s]+", "", new_text)
    neg_markers = ("禁止", "ならない", "べきではない", "反対")
    cond_markers = ("条件", "限り", "場合のみ", "開示", "明記")
    new_neg = any(m in norm_new for m in neg_markers)
    new_cond = any(m in norm_new for m in cond_markers)

    g_new = _char_ngrams(norm_new, 2)
    best: tuple[float, int, str] | None = None
    for sid, body in existing:
        norm_old = re.sub(r"[。、\s]+", "", body)
        if norm_new == norm_old:
            return (sid, body)
        if (any(m in norm_old for m in neg_markers) != new_neg) or (
            any(m in norm_old for m in cond_markers) != new_cond
        ):
            continue
        g_old = _char_ngrams(norm_old, 2)
        jaccard = len(g_new & g_old) / max(1, len(g_new | g_old))
        seq = SequenceMatcher(None, norm_new, norm_old).ratio()
        sim = 0.5 * jaccard + 0.5 * seq
        if sim >= 0.85 and (best is None or sim > best[0]):
            best = (sim, sid, body)
    return (best[1], best[2]) if best else None


# ---------- P3 立場の軸の提案 ----------
def suggest_axes(title: str, description: str) -> dict[str, Any]:
    text = f"{title} {description}"
    if any(k in text for k in ("教育", "学校", "授業", "教員", "先生", "生徒", "学習")):
        axes = [
            {
                "name": "教育現場との関わり方",
                "options": ["教員・学校現場", "生徒・学生", "保護者", "AI開発・教育事業者", "当てはまらない"],
                "why_divergent": "指導の責任を負う側、学ぶ側、見守る側で、効率化と学習機会のバランス感覚が異なるため",
            },
            {
                "name": "日常での生成AIの利用頻度",
                "options": ["ほぼ毎日使う", "週に数回使う", "ほとんど使わない", "当てはまらない"],
                "why_divergent": "実際の利用経験によって、AIの限界やリスクの肌感覚が大きく変わるため",
            },
        ]
    elif any(k in text for k in ("クリエイ", "著作", "イラスト", "制作", "学習データ", "表現")):
        axes = [
            {
                "name": "制作・AIとの関わり方",
                "options": ["創作者・クリエイター", "AI開発・提供者", "AIを活用する制作者", "コンテンツ利用者", "当てはまらない"],
                "why_divergent": "作品の権利を守る立場と、技術を開発・活用する立場で利害やリスク構造が異なるため",
            },
            {
                "name": "創作活動の位置づけ",
                "options": ["生業・本業としている", "副業・趣味で行っている", "鑑賞・消費が中心", "当てはまらない"],
                "why_divergent": "収入やキャリアへの直接的な影響度によって求める保護水準が異なるため",
            },
        ]
    else:
        axes = [
            {
                "name": "このテーマとの関わり方",
                "options": ["提供する・作る側", "現場で使う・実践する側", "管理・ルールを決める側", "影響を受ける市民・利用者", "当てはまらない"],
                "why_divergent": "技術や制度を作る側・現場で運用する側・影響を受ける側で見えているリスクや負担が異なるため",
            },
            {
                "name": "変化と安全性のどちらを重視するか（立場上の制約）",
                "options": ["現場の負担軽減・スピード重視", "安全性・公平性の担保を最優先", "ケースバイケース", "当てはまらない"],
                "why_divergent": "失敗時の責任の重さや現場の逼迫度によって優先順位が分かれるため",
            },
        ]
    return {"axes": axes, "ai": "mock"}


# ---------- P4 体験談の匿名化・要約 ----------
def anonymize_story(body: str) -> dict[str, Any]:
    masked = body.strip()
    masked_items: list[str] = []

    patterns: list[tuple[str, str, str]] = [
        (r"\d{4}年\d{1,2}月(\d{1,2}日)?", "[時期]", "具体的な日付"),
        (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[メールアドレス]", "メールアドレス"),
        (r"0\d{1,4}-\d{1,4}-\d{4}", "[電話番号]", "電話番号"),
        (r"[^\s、。]{2,10}(小学校|中学校|高等学校|高校|大学|学園)", "[学校名]", "学校名"),
        (r"(株式会社|有限会社)[^\s、。]{1,12}|[^\s、。]{1,12}(株式会社|社)", "[企業名]", "企業名"),
        (r"[^\s、。]{1,6}(都|道|府|県)[^\s、。]{1,8}(市|区|町|村)", "[地域名]", "具体的な自治体名"),
    ]
    for pat, repl, label in patterns:
        if re.search(pat, masked):
            masked = re.sub(pat, repl, masked)
            if label not in masked_items:
                masked_items.append(label)

    clean_one_line = re.sub(r"\s+", " ", masked)
    summary = clean_one_line if len(clean_one_line) <= 78 else clean_one_line[:75] + "…"
    return {
        "masked_body": masked,
        "summary": summary,
        "masked_items": masked_items,
        "ai": "mock",
    }


# ---------- P5 条件付き合意案の生成 ----------
def generate_bridges(
    statement_text: str,
    support_stories: list[tuple[int, str]],
    oppose_stories: list[tuple[int, str]],
    boundary_stories: list[tuple[int, str]],
) -> dict[str, Any]:
    sup_summary = support_stories[0][1] if support_stories else "現場の負担軽減や実用上のメリット"
    opp_summary = oppose_stories[0][1] if oppose_stories else "安全性・公平性や思考機会が失われることへの懸念"

    core = re.sub(r"(すべきだ|すべきである|してほしい|してはならない|べきではない)。?$", "", statement_text).strip()
    core = core[:42]

    story_ids = [sid for sid, _ in (support_stories[:1] + oppose_stories[:1] + boundary_stories[:1])]

    candidates = [
        {
            "text": f"利用履歴や根拠の開示と、不利益が生じない確認手順を条件として、{core}を認めるべきだ"[:80],
            "grounded_in_story_ids": story_ids,
        },
        {
            "text": f"基礎的な理解や安全確認が済んだ段階に限り、段階的に{core}を導入すべきだ"[:80],
            "grounded_in_story_ids": story_ids,
        },
    ]

    return {
        "concerns": {
            "support_side": f"賛成側が重視している点：{sup_summary[:70]}",
            "oppose_side": f"反対側が懸念している点：{opp_summary[:70]}",
        },
        "bridge_principles": candidates,
        "ai": "mock",
    }


# ---------- P6 成果物の文章化 ----------
def compile_report(
    topic_title: str,
    topic_desc: str,
    version: str,
    n_participants: int,
    position_counts: dict[str, dict[str, int]],
    params: dict[str, Any],
    sections_data: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """数値ルールで分類された結果から、引用マーカー [S:id] / [T:id] つきの Markdown 成果物を作る。"""
    citations: list[dict[str, Any]] = []
    lines: list[str] = []

    lines.append(f"# {topic_title} ― 成果物レポート（v{version}）")
    lines.append("")
    lines.append(f"> {topic_desc}")
    lines.append("")
    lines.append("## はじめに（参加者と集計方法）")
    lines.append("")
    lines.append(
        f"本ドキュメントは、参加者 **{n_participants}名** の投票および投稿された原体験をもとに、"
        f"数値ルール（合意閾値 {int(params.get('consensus_rate', 0.7) * 100)}%、"
        f"分岐点の立場間ギャップ {int(params.get('divergence_gap', 0.3) * 100)}pt 以上・統計的有意水準 q < {params.get('divergence_q', 0.05)}）"
        f"によって自動編纂された成果物です。"
    )
    lines.append("")

    # 1. 共通原則
    lines.append("## 1. 立場を越えた共通原則")
    lines.append("")
    consensus = sections_data.get("consensus", [])
    if not consensus:
        lines.append("現在、すべての立場で基準を満たした共通原則はまだありません。")
        lines.append("")
    else:
        lines.append("すべての立場（10名以上のグループ）において70%以上の賛成が得られた、議論の土台となる原則です。")
        lines.append("")
        for item in consensus:
            sid = item["id"]
            citations.append({"section_key": "consensus", "ref_type": "statement", "ref_id": sid})
            rate_str = " / ".join(f"{g}: {int(round(r * 100))}%" for g, r in item.get("group_rates", [])[:4])
            lines.append(f"- **{item['body']}** [S:{sid}]")
            if rate_str:
                lines.append(f"  - 立場別の賛成率：{rate_str}")
            for st in item.get("stories", [])[:2]:
                citations.append({"section_key": "consensus", "ref_type": "story", "ref_id": st["id"]})
                pos_lbl = f"（{st['author_position_label']}）" if st.get("author_position_label") else ""
                lines.append(f"  - 背景の原体験{pos_lbl}：{st['summary']} [T:{st['id']}]")
        lines.append("")

    # 2. 立場による分岐点
    lines.append("## 2. 立場によって見え方が大きく違う論点（分岐点）")
    lines.append("")
    divergences = sections_data.get("divergence", [])
    if not divergences:
        lines.append("現在、統計的に有意な立場間の分岐点は検出されていません。")
        lines.append("")
    else:
        lines.append(
            "立場によって賛否が大きく分かれている論点です。利害の違いによるものか、"
            "その立場でしか見えない現場の経験によるものかを理解するため、双方の原体験を併記しています。"
        )
        lines.append("")
        for item in divergences:
            sid = item["id"]
            citations.append({"section_key": "divergence", "ref_type": "statement", "ref_id": sid})
            gap_pt = int(round((item.get("gap") or 0) * 100))
            dim_lbl = item.get("gap_dimension_label") or "立場"
            lines.append(f"### {item['body']} [S:{sid}]")
            lines.append(f"- **最大差 {gap_pt}ポイント**（主な軸：{dim_lbl}）")
            if item.get("group_rates"):
                rate_str = " ／ ".join(f"{g} 賛成 {int(round(r * 100))}%" for g, r in item["group_rates"])
                lines.append(f"- 立場別の内訳：{rate_str}")
            sup_stories = [s for s in item.get("stories", []) if s["stance"] == "supports"]
            opp_stories = [s for s in item.get("stories", []) if s["stance"] == "opposes"]
            bnd_stories = [s for s in item.get("stories", []) if s.get("is_boundary")]
            if sup_stories:
                st = sup_stories[0]
                citations.append({"section_key": "divergence", "ref_type": "story", "ref_id": st["id"]})
                pos_lbl = f"（{st['author_position_label']}）" if st.get("author_position_label") else ""
                lines.append(f"- **賛成側の原体験**{pos_lbl}：{st['summary']} [T:{st['id']}]")
            if opp_stories:
                st = opp_stories[0]
                citations.append({"section_key": "divergence", "ref_type": "story", "ref_id": st["id"]})
                pos_lbl = f"（{st['author_position_label']}）" if st.get("author_position_label") else ""
                lines.append(f"- **反対側の原体験**{pos_lbl}：{st['summary']} [T:{st['id']}]")
            if bnd_stories:
                st = bnd_stories[0]
                citations.append({"section_key": "divergence", "ref_type": "story", "ref_id": st["id"]})
                pos_lbl = f"（{st['author_position_label']}）" if st.get("author_position_label") else ""
                lines.append(f"- **立場を越えた体験（多数派と異なる視点）**{pos_lbl}：{st['summary']} [T:{st['id']}]")
            lines.append("")

    # 3. 条件付き合意案
    lines.append("## 3. 条件付き合意案（橋渡し原則）")
    lines.append("")
    bridges = sections_data.get("bridge", [])
    if not bridges:
        lines.append("現在、すべての立場から55%以上の賛成を得た条件付き合意案はまだありません。")
        lines.append("")
    else:
        lines.append("双方の懸念を踏まえた条件をつけることで、すべての立場から一定の賛成（55%以上）を得た原則です。")
        lines.append("")
        for item in bridges:
            sid = item["id"]
            citations.append({"section_key": "bridge", "ref_type": "statement", "ref_id": sid})
            rate_str = " / ".join(f"{g}: {int(round(r * 100))}%" for g, r in item.get("group_rates", [])[:4])
            lines.append(f"- **{item['body']}** [S:{sid}]")
            if rate_str:
                lines.append(f"  - 立場別の賛成率：{rate_str}")
        lines.append("")

    # 4. 立場によらず意見が割れている論点
    lines.append("## 4. 立場によらず意見が割れている論点")
    lines.append("")
    vsplits = sections_data.get("value_split", [])
    if not vsplits:
        lines.append("現在、該当する論点はありません。")
        lines.append("")
    else:
        lines.append("賛否は拮抗していますが、立場の違いでは説明できない（個人の価値観や経験によって分かれている）論点です。")
        lines.append("")
        for item in vsplits:
            sid = item["id"]
            citations.append({"section_key": "value_split", "ref_type": "statement", "ref_id": sid})
            lines.append(f"- **{item['body']}** [S:{sid}]")
            for st in item.get("stories", [])[:2]:
                citations.append({"section_key": "value_split", "ref_type": "story", "ref_id": st["id"]})
                lines.append(f"  - 視点：{st['summary']} [T:{st['id']}]")
        lines.append("")

    # 5. この成果物の限界
    lines.append("## 5. この成果物の限界（参加者の構成）")
    lines.append("")
    lines.append("- 本議論は自由参加形式で行われており、統計的な無作為抽出ではありません。")
    for dim_label, counts in position_counts.items():
        breakdown = "、".join(f"{k}: {v}名" for k, v in counts.items())
        lines.append(f"- **{dim_label}** の参加者内訳：{breakdown}")

    return {
        "body_md": "\n".join(lines),
        "citations": citations,
        "generator": "template",
    }
