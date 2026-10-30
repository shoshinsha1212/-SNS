"""初回起動時のサンプルデータ投入（シード）。

80名の参加者（4つの立場×各20名、最小人数ルール10名以上を満たす）と、
12件の原則（共通原則・立場による分岐点・条件付き合意案・価値観による分岐がすべて現れる構成）、
および双方の体験談と「立場を越えた体験（境界人）」を投入し、初回の分析と成果物 v1.0 を生成する。
"""

from __future__ import annotations

import secrets

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    PositionAxis,
    PositionOption,
    Statement,
    Story,
    StoryReaction,
    StoryStatementLink,
    Topic,
    User,
    UserAttribute,
    UserTopicPosition,
    VoteEvent,
)
from .services.analysis_service import get_user_position_snapshot, run_analysis


def ensure_seeded(db: Session) -> None:
    existing = db.scalars(select(Topic)).first()
    if existing is not None:
        return

    rng = np.random.default_rng(2026)

    topic = Topic(
        title="教育現場での生成AI活用と行動原則",
        description=(
            "学校や学習の場で生成AIをどう使い、どこに歯止めをかけるべきか。"
            "教員・生徒・保護者・開発者のそれぞれの現場のリアル（原体験）を持ち寄り、"
            "共通の原則と立場ごとの分岐点を整理します。"
        ),
        status="open",
    )
    db.add(topic)
    db.flush()

    ax1 = PositionAxis(topic_id=topic.id, name="教育現場との関わり方", source="ai_proposed", order=0)
    ax2 = PositionAxis(topic_id=topic.id, name="日常での生成AIの利用頻度", source="ai_proposed", order=1)
    db.add_all([ax1, ax2])
    db.flush()

    pos_labels = ["教員・学校現場", "生徒・学生", "保護者", "AI開発・教育事業者"]
    pos_opts: dict[str, PositionOption] = {}
    for lbl in pos_labels + ["当てはまらない"]:
        opt = PositionOption(axis_id=ax1.id, label=lbl)
        db.add(opt)
        pos_opts[lbl] = opt

    freq_labels = ["ほぼ毎日使う", "週に数回使う", "ほとんど使わない"]
    freq_opts: dict[str, PositionOption] = {}
    for lbl in freq_labels + ["当てはまらない"]:
        opt = PositionOption(axis_id=ax2.id, label=lbl)
        db.add(opt)
        freq_opts[lbl] = opt
    db.flush()

    age_by_pos = {
        "教員・学校現場": ["30代・40代", "50代以上"],
        "生徒・学生": ["10代・20代"],
        "保護者": ["30代・40代", "50代以上"],
        "AI開発・教育事業者": ["10代・20代", "30代・40代"],
    }
    role_by_pos = {
        "教員・学校現場": "現場・実務中心",
        "生徒・学生": "学生・市民・その他",
        "保護者": "学生・市民・その他",
        "AI開発・教育事業者": "企画・専門職",
    }

    users_by_pos: dict[str, list[User]] = {p: [] for p in pos_labels}
    for p_idx, p_label in enumerate(pos_labels):
        for i in range(20):
            u = User(
                handle=f"{p_label[:2]}参加者{i + 1:02d}",
                token=secrets.token_hex(16),
                trust_level=1,
                is_synthetic=True,
            )
            db.add(u)
            db.flush()
            age_val = age_by_pos[p_label][i % len(age_by_pos[p_label])]
            db.add(UserAttribute(user_id=u.id, key="age_band", value=age_val))
            db.add(UserAttribute(user_id=u.id, key="role_style", value=role_by_pos[p_label]))
            db.add(
                UserTopicPosition(
                    user_id=u.id,
                    topic_id=topic.id,
                    axis_id=ax1.id,
                    option_id=pos_opts[p_label].id,
                )
            )
            f_lbl = freq_labels[(p_idx + i) % len(freq_labels)]
            db.add(
                UserTopicPosition(
                    user_id=u.id,
                    topic_id=topic.id,
                    axis_id=ax2.id,
                    option_id=freq_opts[f_lbl].id,
                )
            )
            users_by_pos[p_label].append(u)
    db.flush()

    # 原則の定義：(本文, origin, 立場ごとの賛成確率 [教員, 生徒, 保護者, 開発者])
    stmt_specs: list[tuple[str, str, list[float]]] = [
        # 1〜3: 立場を越えた共通原則（すべての立場で 80%〜95% 賛成）
        (
            "生成AIが誤りや偏りを含みうることと、事実確認の方法をすべての児童・生徒に教えるべきだ",
            "seed",
            [0.95, 0.90, 0.95, 0.95],
        ),
        (
            "児童・生徒の個人情報や成績・相談記録を、外部のAIの学習データとして送信してはならない",
            "seed",
            [0.95, 0.90, 0.95, 0.90],
        ),
        (
            "障害や日本語の習熟度に応じた個別支援（読み上げ・やさしい日本語化など）にはAIを積極的に活用すべきだ",
            "user",
            [0.90, 0.90, 0.85, 0.95],
        ),
        # 4〜7: 立場によって見え方が大きく違う論点（分岐点）
        (
            "教員の教材作成・校務文書・テスト作問の補助には、生成AIの利用を全面的に認めるべきだ",
            "ai_from_complaint",
            [0.90, 0.65, 0.20, 0.90],
        ),
        (
            "読書感想文や探究レポートなどの宿題では、生成AIの使用を一律に禁止すべきだ",
            "user",
            [0.80, 0.15, 0.85, 0.20],
        ),
        (
            "授業で使うAIツールは、国や教育委員会が安全性を審査・認証したものだけに限定すべきだ",
            "seed",
            [0.65, 0.25, 0.90, 0.15],
        ),
        (
            "生徒が自分の考えを整理する壁打ち相手として、授業中に自由にAIチャットを使えるようにすべきだ",
            "user",
            [0.25, 0.90, 0.30, 0.85],
        ),
        (
            "AIによる採点・評価補助を導入し、定期テストや小テストの採点業務を自動化すべきだ",
            "user",
            [0.85, 0.30, 0.25, 0.90],
        ),
        # 8〜9: 条件付き合意案（橋渡し原則）
        (
            "AIを使った箇所と対話履歴を提出時に明記することを条件として、レポート課題でのAI活用を認めるべきだ",
            "ai_bridge",
            [0.75, 0.80, 0.70, 0.85],
        ),
        (
            "教員が最終確認し判断の根拠を説明できる場合に限り、校務や教材作成でのAI利用を認めるべきだ",
            "ai_bridge",
            [0.85, 0.75, 0.75, 0.85],
        ),
        # 10〜11: 立場によらず意見が割れている論点（価値観の分岐）
        (
            "小学校の段階から、プログラミングと同様に生成AIとの対話技術を必修化すべきだ",
            "seed",
            [0.50, 0.55, 0.45, 0.55],
        ),
        (
            "AIが悩みを聞くスクールカウンセリング補助を導入し、相談のハードルを下げるべきだ",
            "user",
            [0.45, 0.55, 0.45, 0.50],
        ),
    ]

    statements: list[Statement] = []
    for idx, (body, origin, _) in enumerate(stmt_specs):
        author = users_by_pos[pos_labels[idx % 4]][0]
        st = Statement(topic_id=topic.id, author_id=author.id, body=body, origin=origin, status="active")
        db.add(st)
        statements.append(st)
    db.flush()

    # 各ユーザーの立場スナップショットをキャッシュして投票を生成
    snap_by_user: dict[int, dict[str, str]] = {}
    for p_label in pos_labels:
        for u in users_by_pos[p_label]:
            snap_by_user[u.id] = get_user_position_snapshot(db, u.id, topic.id)

    for s_idx, (_, _, probs) in enumerate(stmt_specs):
        st = statements[s_idx]
        for p_idx, p_label in enumerate(pos_labels):
            p_agree = probs[p_idx]
            for u_idx, u in enumerate(users_by_pos[p_label]):
                # 各立場の一部の人（u_idx == 19）は「境界人」として、分岐点で逆の票を入れるようにする
                if s_idx in (3, 4, 5, 6) and u_idx == 19:
                    val = -1 if p_agree >= 0.5 else 1
                else:
                    val = 1 if rng.random() < p_agree else -1
                db.add(
                    VoteEvent(
                        user_id=u.id,
                        statement_id=st.id,
                        topic_id=topic.id,
                        value=val,
                        position_snapshot=snap_by_user[u.id],
                    )
                )
    db.flush()

    # 体験談（賛成側・反対側・境界人のストーリー）
    story_specs = [
        # 原則4（教員の校務・教材作成でのAI利用）
        (
            3,
            users_by_pos["教員・学校現場"][0],
            "present",
            "supports",
            "プリント作成と保護者文書のたたき台をAIで作ることで、放課後に生徒と向き合う時間が週4時間増えました。",
            "中学校で担任をしています。これまでテストの作問や学年便りの下書きで毎日21時まで残業していましたが、"
            "AIにたたき台を作らせて自分で手直しするようになってから、放課後に不登校気味の生徒とゆっくり話す時間が週に4時間ほど確保できるようになりました。",
        ),
        (
            3,
            users_by_pos["保護者"][0],
            "future",
            "opposes",
            "先生からの所見やコメントまでAIの定型文になったら、子どもを本当に見てくれているのか信頼できなくなる懸念があります。",
            "小学生の子どもを持つ保護者です。業務が大変なのは理解しますが、通知表の所見や連絡帳のやりとりまでAIで作られたら、"
            "『先生はうちの子をちゃんと見てくれているのか』と不信感を持ってしまうと思います。手抜きに使われる未来が不安です。",
        ),
        (
            3,
            users_by_pos["保護者"][19],  # 保護者の境界人（賛成に投票）
            "past",
            "supports",
            "担任の先生が過労で休職した経験から、事務作業はAIに任せて先生の健康と授業の質を守るべきだと考えるようになりました。",
            "昨年、子どもの担任の先生が長時間労働で年度途中に休職してしまい、クラスが荒れてしまった経験があります。"
            "最初はAIに頼るなんてと思っていましたが、先生が倒れてしまっては元も子もありません。事務や下準備こそAIに任せるべきだと思います。",
        ),
        # 原則5（宿題・レポートでのAI一律禁止）
        (
            4,
            users_by_pos["教員・学校現場"][1],
            "past",
            "supports",
            "夏休みの読書感想文でAI丸写しの提出が相次ぎ、自分の言葉で考える力が育たない危機感を覚えました。",
            "高校の国語科です。昨年の課題で、明らかに生成AIの出力をそのまま写した感想文がクラスで数名出ました。"
            "本人に質問しても内容が頭に入っておらず、試行錯誤して自分の言葉を探す経験そのものが失われると強く危惧しています。",
        ),
        (
            4,
            users_by_pos["生徒・学生"][0],
            "present",
            "opposes",
            "学校で一律禁止されても自宅では皆使っており、正しい使い方を教わらないまま隠れて使う方が危険です。",
            "高校生です。学校のルールで『AI禁止』と言われても、実際にはスマホでみんな使っています。"
            "一律に禁止されると、どういう使い方がズルでどういう使い方が学習になるのかを先生に相談できなくなり、かえって丸写しが増えると思います。",
        ),
        (
            4,
            users_by_pos["教員・学校現場"][19],  # 教員の境界人（一律禁止に反対）
            "past",
            "opposes",
            "文章を書くのが極端に苦手な生徒が、AIと対話して構成を作ったことで初めて自分の体験をレポートに書けました。",
            "以前、白紙提出が続いていた生徒に、AIにインタビューしてもらいながら構成メモを作る方法を試したところ、"
            "初めて自分の言葉で最後までレポートを書き上げることができました。一律禁止はその芽まで摘んでしまいます。",
        ),
        # 原則6（公的認証ツールのみに限定）
        (
            5,
            users_by_pos["保護者"][1],
            "present",
            "supports",
            "誤情報や不適切な広告・誘導から子どもを守るため、学校で使うツールには公的な安全基準が必要です。",
            "家庭ではどのAIアプリが安全なのか判断しきれません。学校で導入する以上は、個人情報の扱いや年齢制限を含めて、"
            "公的な機関が安全性を確認したものに限定してほしいです。",
        ),
        (
            5,
            users_by_pos["AI開発・教育事業者"][0],
            "present",
            "opposes",
            "公的認証だけに絞ると数ヶ月〜数年遅れのモデルしか使えず、現場の工夫や最新のアクセシビリティ機能が閉ざされます。",
            "教育向けツールを開発しています。硬直的な事前認証制にすると、審査に1年以上かかり、"
            "その間に改善された誤情報対策や視覚・聴覚支援の機能が学校現場に届かなくなってしまいます。",
        ),
        # 原則3（障害や日本語習熟度に応じた個別支援）
        (
            2,
            users_by_pos["教員・学校現場"][2],
            "past",
            "supports",
            "外国にルーツのある児童へのプリントをAIでやさしい日本語と母語併記にしたところ、授業への参加が一変しました。",
            "日本語がまだ十分でない転入生がいた際、授業プリントをAIで『ルビつきのやさしい日本語』と母語訳に即時変換して渡したところ、"
            "初めてグループワークで自分の意見を発表できました。",
        ),
    ]

    for s_idx, author, kind, stance, summary, body in story_specs:
        st_obj = Story(
            author_id=author.id,
            topic_id=topic.id,
            kind=kind,
            body=body,
            summary=summary,
            anonymization="none",
            position_snapshot=snap_by_user[author.id],
        )
        db.add(st_obj)
        db.flush()
        db.add(StoryStatementLink(story_id=st_obj.id, statement_id=statements[s_idx].id, stance=stance))

        # 異なる立場からの「理解できた」反応と、同じ立場からの「共感」反応を付与
        for p_label in pos_labels:
            for u in users_by_pos[p_label][:4]:
                if u.id == author.id:
                    continue
                r_kind = "resonate" if snap_by_user[u.id].get(f"axis:{ax1.id}") == snap_by_user[author.id].get(f"axis:{ax1.id}") else "understand"
                db.add(
                    StoryReaction(
                        user_id=u.id,
                        story_id=st_obj.id,
                        kind=r_kind,
                        position_snapshot=snap_by_user[u.id],
                    )
                )

    db.commit()
    run_analysis(db, topic.id)
