"""シードおよびテストデータ管理モジュール。

32名の合成ペルソナ（19〜22歳）が4日間にわたり、
1日あたり5〜20回サイト上で行動（投票、ストーリー投稿、リアクション、新原則起案、レポート閲覧）
したリアルなテスト運用データを永続化し、サイト上に完全な形で残します。
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    AnalysisSnapshot,
    Contribution,
    GroupStats,
    PositionAxis,
    PositionOption,
    ReportCitation,
    ReportVersion,
    Statement,
    StatementStats,
    Story,
    StoryReaction,
    StoryStatementLink,
    Topic,
    User,
    UserAttribute,
    UserProjection,
    UserTopicPosition,
    VoteEvent,
    utcnow,
)
from .seed_topics_data import NEW_TOPICS_SPECS, PERSONA_CONTRIBUTIONS
from .services.analysis_service import get_user_position_snapshot, run_analysis

INITIAL_STATEMENTS: list[tuple[str, str, list[float]]] = [
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


def seed_initial_topic_and_statements(db: Session) -> Topic:
    """トピックと初期論点（12件）がなければ作成する。"""
    topic = db.scalars(select(Topic)).first()
    if topic is None:
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

    # 立場軸の作成（存在しない場合）
    ax1 = db.scalars(select(PositionAxis).where(PositionAxis.topic_id == topic.id, PositionAxis.order == 0)).first()
    if not ax1:
        ax1 = PositionAxis(topic_id=topic.id, name="教育現場との関わり方", source="ai_proposed", order=0)
        db.add(ax1)
        db.flush()
        pos_labels = ["教員・学校現場", "生徒・学生", "保護者", "AI開発・教育事業者", "当てはまらない"]
        for lbl in pos_labels:
            db.add(PositionOption(axis_id=ax1.id, label=lbl))

    ax2 = db.scalars(select(PositionAxis).where(PositionAxis.topic_id == topic.id, PositionAxis.order == 1)).first()
    if not ax2:
        ax2 = PositionAxis(topic_id=topic.id, name="日常での生成AIの利用頻度", source="ai_proposed", order=1)
        db.add(ax2)
        db.flush()
        freq_labels = ["ほぼ毎日使う", "週に数回使う", "ほとんど使わない", "当てはまらない"]
        for lbl in freq_labels:
            db.add(PositionOption(axis_id=ax2.id, label=lbl))
    db.flush()

    # 運営アカウント
    admin = db.scalars(select(User).where(User.handle == "運営チーム")).first()
    if not admin:
        admin = User(handle="運営チーム", token=secrets.token_hex(16), trust_level=9, is_synthetic=False)
        db.add(admin)
        db.flush()

    # 初期論点（12件）の作成（存在しない場合）
    existing_stmts = list(db.scalars(select(Statement).where(Statement.topic_id == topic.id)).all())
    if not existing_stmts:
        for body, origin, _ in INITIAL_STATEMENTS:
            st = Statement(
                topic_id=topic.id,
                author_id=admin.id,
                body=body,
                origin=origin,
                status="active",
            )
            db.add(st)
        db.flush()

    db.commit()
    return topic


# 32名のペルソナ定義（19〜22歳、全クラスター網羅）
# 3つの主要立場に 11名 / 11名 / 10名 で配分し、最小人数ルール (>=10名) を完全に満たす
PERSONAS_32 = [
    # --- 立場1: 教員・学校現場 (11名) ---
    {"handle": "陸 (教育4年/実習生)", "axis1": "教員・学校現場", "axis2": "週に数回使う", "role": "現場・実務中心", "votes_12": [1, 1, 1, 1, -1, 1, 1, 1, 1, 1, 1, 1]}, # 境界人(S5反対)
    {"handle": "奈央 (地方教育2年)", "axis1": "教員・学校現場", "axis2": "ほとんど使わない", "role": "現場・実務中心", "votes_12": [1, 1, 1, 1, 1, 1, -1, 1, 1, 1, 0, 1]},
    {"handle": "健太 (社会3年/塾講師)", "axis1": "教員・学校現場", "axis2": "週に数回使う", "role": "現場・実務中心", "votes_12": [1, 1, 1, 1, 1, 1, -1, 1, 1, 1, 1, 1]},
    {"handle": "美咲 (文1年/家庭教師)", "axis1": "教員・学校現場", "axis2": "ほとんど使わない", "role": "現場・実務中心", "votes_12": [1, 1, 1, 1, 1, 1, -1, 1, 1, 1, -1, 1]},
    {"handle": "翔 (国際教養4年/TA)", "axis1": "教員・学校現場", "axis2": "週に数回使う", "role": "現場・実務中心", "votes_12": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]},
    {"handle": "大輝 (理学4年/TA院進)", "axis1": "教員・学校現場", "axis2": "ほぼ毎日使う", "role": "現場・実務中心", "votes_12": [1, 1, 1, 1, -1, 1, 1, 1, 1, 1, 1, 1]}, # 境界人(S5反対)
    {"handle": "萌花 (短大保育1年/実習)", "axis1": "教員・学校現場", "axis2": "ほとんど使わない", "role": "現場・実務中心", "votes_12": [1, 1, 1, 1, 1, 1, -1, -1, 1, 1, -1, 1]},
    {"handle": "結菜 (看護2年/指導補佐)", "axis1": "教員・学校現場", "axis2": "ほとんど使わない", "role": "現場・実務中心", "votes_12": [1, 1, 1, 1, 1, 1, -1, -1, 1, 1, -1, 1]},
    {"handle": "志保 (薬学3年/実習生)", "axis1": "教員・学校現場", "axis2": "週に数回使う", "role": "現場・実務中心", "votes_12": [1, 1, 1, 1, 1, 1, -1, 1, 1, 1, 1, -1]},
    {"handle": "美優 (事務員/校務支援)", "axis1": "教員・学校現場", "axis2": "週に数回使う", "role": "現場・実務中心", "votes_12": [1, 1, 1, 1, 1, 1, -1, 1, 1, 1, 0, 1]},
    {"handle": "健二 (公務員浪人/指導員)", "axis1": "教員・学校現場", "axis2": "ほとんど使わない", "role": "現場・実務中心", "votes_12": [1, 1, 1, 1, 1, 1, -1, 1, 1, 1, 1, 0]},

    # --- 立場2: 生徒・学生 (11名) ---
    {"handle": "葵 (法学部2年)", "axis1": "生徒・学生", "axis2": "週に数回使う", "role": "学生・市民・その他", "votes_12": [1, 1, 1, 1, -1, -1, 1, 1, 1, 1, 0, 1]},
    {"handle": "蓮 (経済3年)", "axis1": "生徒・学生", "axis2": "ほぼ毎日使う", "role": "学生・市民・その他", "votes_12": [1, 1, 1, 1, -1, -1, 1, 1, 1, 1, 1, 1]},
    {"handle": "隼人 (理工2年)", "axis1": "生徒・学生", "axis2": "ほぼ毎日使う", "role": "学生・市民・その他", "votes_12": [1, 1, 1, 1, -1, -1, 1, 1, 1, 1, 1, 1]},
    {"handle": "陽菜 (心理3年)", "axis1": "生徒・学生", "axis2": "週に数回使う", "role": "学生・市民・その他", "votes_12": [1, 1, 1, 1, -1, 1, 1, 0, 1, 1, -1, 1]},
    {"handle": "栞 (文系3年)", "axis1": "生徒・学生", "axis2": "週に数回使う", "role": "学生・市民・その他", "votes_12": [1, 1, 1, 1, -1, 1, 1, -1, 1, 1, -1, 0]},
    {"handle": "奏太 (音響専門2年)", "axis1": "生徒・学生", "axis2": "週に数回使う", "role": "学生・市民・その他", "votes_12": [1, 1, 1, 1, 1, 1, -1, -1, 1, 1, -1, 0]}, # 境界人(S5賛成)
    {"handle": "瑠美 (生活科学4年)", "axis1": "生徒・学生", "axis2": "ほとんど使わない", "role": "学生・市民・その他", "votes_12": [1, 1, 1, 1, -1, 1, 1, 0, 1, 1, -1, 1]},
    {"handle": "玲奈 (メディア2年)", "axis1": "生徒・学生", "axis2": "ほぼ毎日使う", "role": "学生・市民・その他", "votes_12": [1, 1, 1, 1, -1, -1, 1, 1, 1, 1, 1, 1]},
    {"handle": "莉子 (美容専門1年)", "axis1": "生徒・学生", "axis2": "週に数回使う", "role": "学生・市民・その他", "votes_12": [1, 1, 1, 1, -1, 1, 1, 1, 1, 1, 0, 1]},
    {"handle": "俊介 (法学部3年/ROM)", "axis1": "生徒・学生", "axis2": "ほとんど使わない", "role": "学生・市民・その他", "votes_12": [1, 1, 1, 1, -1, 1, 1, 1, 1, 1, -1, 0]},
    {"handle": "綾香 (通信制大1年)", "axis1": "生徒・学生", "axis2": "週に数回使う", "role": "学生・市民・その他", "votes_12": [1, 1, 1, 1, -1, 1, 1, 1, 1, 1, -1, 1]},

    # --- 立場3: AI開発・教育事業者 (10名) ---
    {"handle": "拓海 (情報3年/エンジニア)", "axis1": "AI開発・教育事業者", "axis2": "ほぼ毎日使う", "role": "企画・専門職", "votes_12": [1, 1, 1, 1, -1, -1, 1, 1, 1, 1, 1, 0]},
    {"handle": "遥 (商学4年/EdTech内定)", "axis1": "AI開発・教育事業者", "axis2": "ほぼ毎日使う", "role": "企画・専門職", "votes_12": [1, 1, 1, 1, -1, -1, 1, 1, 1, 1, 1, 1]},
    {"handle": "航希 (国際4年/学生起業)", "axis1": "AI開発・教育事業者", "axis2": "ほぼ毎日使う", "role": "企画・専門職", "votes_12": [1, 1, 1, 1, -1, -1, 1, 1, 1, 1, 1, 1]},
    {"handle": "恭平 (経営3年/スタートアップ)", "axis1": "AI開発・教育事業者", "axis2": "ほぼ毎日使う", "role": "企画・専門職", "votes_12": [1, 1, 1, 1, -1, -1, 1, 1, 1, 1, 1, 1]},
    {"handle": "渚 (UI/UXデザイナー)", "axis1": "AI開発・教育事業者", "axis2": "ほぼ毎日使う", "role": "企画・専門職", "votes_12": [1, 1, 1, 1, -1, -1, 1, 1, 1, 1, 1, 1]},
    {"handle": "航 (工学部4年/地方国立)", "axis1": "AI開発・教育事業者", "axis2": "週に数回使う", "role": "企画・専門職", "votes_12": [1, 1, 1, 1, -1, -1, 1, 1, 1, 1, 0, 0]},
    {"handle": "颯太 (インフラ若手社員)", "axis1": "AI開発・教育事業者", "axis2": "ほとんど使わない", "role": "現場・実務中心", "votes_12": [1, 1, 1, 1, -1, -1, 1, 1, 1, 1, 1, -1]},
    {"handle": "凛 (アパレル/EC企画)", "axis1": "AI開発・教育事業者", "axis2": "週に数回使う", "role": "現場・実務中心", "votes_12": [1, 1, 1, 1, -1, -1, 1, 1, 1, 1, 0, 1]},
    {"handle": "悠真 (製造業/データ担当)", "axis1": "AI開発・教育事業者", "axis2": "ほとんど使わない", "role": "現場・実務中心", "votes_12": [1, 1, 1, 1, -1, -1, 1, 1, 1, 1, 0, 0]},
    {"handle": "美羽 (Web制作フリーランス)", "axis1": "AI開発・教育事業者", "axis2": "ほとんど使わない", "role": "現場・実務中心", "votes_12": [1, 1, 1, 1, -1, -1, 1, 1, 1, 1, 0, 1]},
]


def seed_4days_32personas(db: Session, topic: Topic) -> None:
    """32名のペルソナが4日間にわたり、1日あたり5〜20回サイト上で行動した実データを構築する。"""
    now = utcnow()
    d1 = now - timedelta(days=3)
    d2 = now - timedelta(days=2)
    d3 = now - timedelta(days=1)
    d4 = now - timedelta(hours=2)

    # 軸とオプションのマッピング取得
    ax1 = db.scalars(select(PositionAxis).where(PositionAxis.topic_id == topic.id, PositionAxis.order == 0)).first()
    ax2 = db.scalars(select(PositionAxis).where(PositionAxis.topic_id == topic.id, PositionAxis.order == 1)).first()
    if not ax1 or not ax2:
        return
    opts1 = {o.label: o for o in db.scalars(select(PositionOption).where(PositionOption.axis_id == ax1.id)).all()}
    opts2 = {o.label: o for o in db.scalars(select(PositionOption).where(PositionOption.axis_id == ax2.id)).all()}

    # 既存の初期論点（12件）を取得
    stmts_12 = list(db.scalars(select(Statement).where(Statement.topic_id == topic.id).order_by(Statement.id)).all())[:12]

    users: list[User] = []
    user_snaps: dict[int, dict[str, str]] = {}

    # ==========================================
    # Day 1: 参加登録、属性・立場設定、前半投票 (S1〜S6)、初期ストーリー投稿
    # ==========================================
    for idx, p in enumerate(PERSONAS_32):
        t_user = d1 + timedelta(minutes=idx * 15)
        u = User(
            handle=p["handle"],
            token=secrets.token_hex(16),
            trust_level=2,
            is_synthetic=False, # 実運用データとして保護
            created_at=t_user,
        )
        db.add(u)
        db.flush()
        users.append(u)

        # 属性
        db.add(UserAttribute(user_id=u.id, key="age_band", value="10代・20代", updated_at=t_user))
        db.add(UserAttribute(user_id=u.id, key="role_style", value=p["role"], updated_at=t_user))

        # 立場
        if p["axis1"] in opts1:
            db.add(UserTopicPosition(user_id=u.id, topic_id=topic.id, axis_id=ax1.id, option_id=opts1[p["axis1"]].id, valid_from=t_user))
        if p["axis2"] in opts2:
            db.add(UserTopicPosition(user_id=u.id, topic_id=topic.id, axis_id=ax2.id, option_id=opts2[p["axis2"]].id, valid_from=t_user))

        db.flush()
        user_snaps[u.id] = get_user_position_snapshot(db, u.id, topic.id)

        # Day 1 投票: S1〜S6 (6問)
        for s_idx in range(6):
            if s_idx < len(stmts_12):
                val = p["votes_12"][s_idx]
                db.add(VoteEvent(
                    user_id=u.id,
                    statement_id=stmts_12[s_idx].id,
                    topic_id=topic.id,
                    value=val,
                    position_snapshot=user_snaps[u.id],
                    created_at=t_user + timedelta(minutes=s_idx * 3 + 2),
                ))

    db.flush()

    # Day 1 ストーリー投稿 (4件)
    day1_stories_spec = [
        # (user_idx, stmt_idx, kind, stance, summary, body)
        (0, 3, "present", "supports", "プリント作成のAI補助で放課後に生徒と向き合う時間が週4時間増えました", "中学校で非常勤講師と教育実習を経験しています。テストの作問や学年便りの下書きで毎日21時まで残業していましたが、AIに素案を作らせて手直しするようになってから、放課後に生徒とゆっくり話す時間が確保できるようになりました。"),
        (11, 4, "present", "opposes", "課題でエラー解消や論理構成の壁打ち相手としてAIが不可欠です", "大学で法律の課題を解く際、判例の論理構成を壁打ち相手としてAIに検証してもらうことで理解が深まりました。これを『一律禁止』にされたら、質問できる環境に恵まれない地方学生や孤独な学生ほど不利になります。"),
        (16, 4, "past", "supports", "芸術課題でAI生成の心のない感想文が並んだのを見てショックを受けました", "音楽表現の授業で、多くの学生がAIに出力させた綺麗な批評文をそのまま提出していました。文法は完璧でも本人の感動が一切入っておらず、感性を育てる授業の意味が失われていると感じました。"),
        (21, 5, "future", "opposes", "公的認証ツール限定は型落ちモデルへの固定化を招き国際競争力を落とします", "教育向けAIアプリを開発しています。教育委員会の審査には1年以上かかります。最先端の安全対策やアクセシビリティ機能を備えた最新モデルが教育現場に届かなくなってしまいます。"),
    ]
    created_stories: list[Story] = []
    for u_idx, s_idx, kind, stance, summary, body in day1_stories_spec:
        author = users[u_idx]
        st_obj = Story(
            author_id=author.id,
            topic_id=topic.id,
            kind=kind,
            body=body,
            summary=summary,
            anonymization="none",
            position_snapshot=user_snaps[author.id],
            created_at=d1 + timedelta(hours=6, minutes=u_idx * 10),
        )
        db.add(st_obj)
        db.flush()
        db.add(StoryStatementLink(story_id=st_obj.id, statement_id=stmts_12[s_idx].id, stance=stance))
        created_stories.append(st_obj)

    # Day 1 リアクション (32件)
    seen_reactions = set()
    for idx, u in enumerate(users):
        target_story = created_stories[idx % len(created_stories)]
        if target_story.author_id != u.id:
            r_kind = "resonate" if idx % 2 == 0 else "understand"
            key = (u.id, target_story.id, r_kind)
            if key not in seen_reactions:
                seen_reactions.add(key)
                db.add(StoryReaction(
                    user_id=u.id,
                    story_id=target_story.id,
                    kind=r_kind,
                    position_snapshot=user_snaps[u.id],
                    created_at=d1 + timedelta(hours=8, minutes=idx * 5),
                ))

    db.flush()

    # ==========================================
    # Day 2: 後半投票 (S7〜S12)、境界人ストーリー投稿、リアクション、成果物 v1.0 生成
    # ==========================================
    for idx, p in enumerate(PERSONAS_32):
        u = users[idx]
        t_day2 = d2 + timedelta(minutes=idx * 12)
        # S7〜S12 への投票 (6問)
        for s_idx in range(6, 12):
            if s_idx < len(stmts_12):
                val = p["votes_12"][s_idx]
                db.add(VoteEvent(
                    user_id=u.id,
                    statement_id=stmts_12[s_idx].id,
                    topic_id=topic.id,
                    value=val,
                    position_snapshot=user_snaps[u.id],
                    created_at=t_day2 + timedelta(minutes=(s_idx - 6) * 3),
                ))

    db.flush()

    # Day 2 ストーリー投稿 (境界人エピソード等 4件)
    day2_stories_spec = [
        # (user_idx, stmt_idx, kind, stance, summary, body)
        (11, 8, "present", "supports", "AIの対話ログ添付を必須にしたことで教授からも公正に評価されました", "ゼミ発表でAIの対話履歴を提出することがルール化されました。どこまでが自分の考えでどこからがAIの提案かが明確になり、教授からも『批判的検討ができている』と評価され、後ろめたさなく使えるようになりました。"),
        (6, 11, "past", "supports", "深夜に誰にも言えない実習の悩みをAIに相談しパニックを乗り越えられました", "実習中に子どもへの対応で失敗し一人で泣いていた夜、AIに話を聞いてもらいました。客観的に『明日はこう切り出してみよう』と励まされ、翌朝無事に実習先に相談できました。"),
        (8, 11, "past", "opposes", "うつの友人がAIに依存し医療機関の受診が半年遅れて悪化してしまいました", "精神的な不調を抱えた友人がAIチャットの無制限な肯定に依存してしまい、専門医療への受診が大幅に遅れました。専門家へのトリアージ機能がないAI単体でのカウンセリングは慎重であるべきです。"),
        (22, 7, "present", "supports", "小テストのAI自動採点で間違えた箇所の即日フィードバックが実現しました", "受講者300人の講義で確認テストの採点がAIで即時集計され、間違えの多かった箇所がその日のうちに解説されるようになりました。教員の負担を減らし学習効率が最大化されています。"),
    ]
    for u_idx, s_idx, kind, stance, summary, body in day2_stories_spec:
        author = users[u_idx]
        st_obj = Story(
            author_id=author.id,
            topic_id=topic.id,
            kind=kind,
            body=body,
            summary=summary,
            anonymization="none",
            position_snapshot=user_snaps[author.id],
            created_at=d2 + timedelta(hours=5, minutes=u_idx * 10),
        )
        db.add(st_obj)
        db.flush()
        db.add(StoryStatementLink(story_id=st_obj.id, statement_id=stmts_12[s_idx].id, stance=stance))
        created_stories.append(st_obj)

    # Day 2 活発なリアクション送信 (重複回避)
    for u in users:
        for offset in range(3):
            t_story = created_stories[(u.id + offset) % len(created_stories)]
            if t_story.author_id != u.id:
                r_kind = "understand" if offset == 1 else "resonate"
                key = (u.id, t_story.id, r_kind)
                if key not in seen_reactions:
                    seen_reactions.add(key)
                    db.add(StoryReaction(
                        user_id=u.id,
                        story_id=t_story.id,
                        kind=r_kind,
                        position_snapshot=user_snaps[u.id],
                        created_at=d2 + timedelta(hours=7, minutes=u.id * 3 + offset * 10),
                    ))

    db.flush()
    # Day 2 終了時点での第1次分析 (v1.0 レポート)
    run_analysis(db, topic.id)

    # ==========================================
    # Day 3: 新規原則 (S13, S14, S15) の起案、相互投票、ストーリー投稿
    # ==========================================
    # S13: 橋本航希 (起業系学生) が起案
    st13 = Statement(
        topic_id=topic.id,
        author_id=users[23].id, # 航希
        body="就職活動において、学生のES作成補助および企業の初期選考における生成AI利用基準を相互に開示すべきだ",
        origin="user",
        status="active",
        created_at=d3 + timedelta(hours=2),
    )
    # S14: 長谷川凛 (社会人) が起案
    st14 = Statement(
        topic_id=topic.id,
        author_id=users[28].id, # 凛
        body="夜間や休日の学校連絡・問い合わせはAIチャットボットによる一次受けを基本とし、教員の時間外直接対応を免除すべきだ",
        origin="ai_from_complaint",
        status="active",
        created_at=d3 + timedelta(hours=3),
    )
    # S15: 石井奏太 (音響専門) が起案
    st15 = Statement(
        topic_id=topic.id,
        author_id=users[16].id, # 奏太
        body="美術・音楽・文学等の創作表現課題では、生成AIを用いた作品と自力制作の作品で評価枠組みを明確に分離すべきだ",
        origin="user",
        status="active",
        created_at=d3 + timedelta(hours=4),
    )
    db.add_all([st13, st14, st15])
    db.flush()

    # 新規原則への32名の投票 (32名 × 3問 = 96票)
    for idx, u in enumerate(users):
        t_day3 = d3 + timedelta(hours=5, minutes=idx * 8)
        val13 = 1 if idx % 10 != 3 else -1
        val14 = 1 if idx % 8 != 0 else -1
        val15 = 1 if idx % 4 != 0 else -1

        db.add(VoteEvent(user_id=u.id, statement_id=st13.id, topic_id=topic.id, value=val13, position_snapshot=user_snaps[u.id], created_at=t_day3))
        db.add(VoteEvent(user_id=u.id, statement_id=st14.id, topic_id=topic.id, value=val14, position_snapshot=user_snaps[u.id], created_at=t_day3 + timedelta(minutes=2)))
        db.add(VoteEvent(user_id=u.id, statement_id=st15.id, topic_id=topic.id, value=val15, position_snapshot=user_snaps[u.id], created_at=t_day3 + timedelta(minutes=4)))

    db.flush()

    # Day 3 ストーリー投稿 (3件)
    day3_stories_spec = [
        (23, st13.id, "present", "supports", "企業はAIでESを足切りしているのに学生のAI利用だけ叱責される理不尽", "就活でESの構成をAIで整えたところ、面接で『自分の言葉ではない』と批判されました。しかしその企業自身が初期選考でAI判定を導入していました。双方の開示ルールが絶対に必要です。"),
        (28, st14.id, "present", "supports", "夜22時の保護者連絡に追われて疲弊する教員の健康を守るAI一次受けの重要性", "学校事務の現場で、夜間の保護者からの緊急性の低いクレーム電話に教員が精神を削られています。夜間はAIが要件を聞き取り翌朝通知する仕組みにすれば離職を防げます。"),
        (16, st15.id, "future", "supports", "AI活用部門と手作業部門を分けることで創作への誠実さと新技術の両立ができる", "音楽コンテストでAI生成曲と生演奏曲が同じ土俵で競わされ紛糾しました。部門を分けることで、技術追求も感性の研鑽もどちらも正当に称えられるはずです。"),
    ]
    for u_idx, st_id, kind, stance, summary, body in day3_stories_spec:
        author = users[u_idx]
        st_obj = Story(
            author_id=author.id,
            topic_id=topic.id,
            kind=kind,
            body=body,
            summary=summary,
            anonymization="none",
            position_snapshot=user_snaps[author.id],
            created_at=d3 + timedelta(hours=8, minutes=u_idx * 5),
        )
        db.add(st_obj)
        db.flush()
        db.add(StoryStatementLink(story_id=st_obj.id, statement_id=st_id, stance=stance))
        created_stories.append(st_obj)

    # Day 3 リアクション (重複回避)
    for u in users:
        for offset in range(2):
            t_story = created_stories[-3 + offset]
            if t_story.author_id != u.id:
                key = (u.id, t_story.id, "resonate")
                if key not in seen_reactions:
                    seen_reactions.add(key)
                    db.add(StoryReaction(
                        user_id=u.id,
                        story_id=t_story.id,
                        kind="resonate",
                        position_snapshot=user_snaps[u.id],
                        created_at=d3 + timedelta(hours=9, minutes=u.id * 4 + offset * 10),
                    ))

    db.flush()

    # ==========================================
    # Day 4: 態度変容・再投票、最終合意形成レポート v2.0 の自動編纂
    # ==========================================
    # 一部のペルソナがストーリーを読んで態度を軟化・再投票 (16名)
    for idx in range(0, 32, 2):
        u = users[idx]
        db.add(VoteEvent(
            user_id=u.id,
            statement_id=stmts_12[4].id,
            topic_id=topic.id,
            value=-1, # 一律禁止には反対だがS9条件付きを支持
            position_snapshot=user_snaps[u.id],
            created_at=d4 + timedelta(minutes=idx * 3),
        ))

    db.commit()

    # Day 4 最終成果物レポート v2.0 の編纂実行
    run_analysis(db, topic.id)
    print("32名×4日間の実テストデータ投入および最新合意形成レポート (v2.0) の編纂が完了しました。")

    # 新規12トピックおよび32名のターゲット別原体験・意見の永続化
    seed_additional_12_topics(db, users)


def seed_additional_12_topics(db: Session, users: list[User]) -> None:
    """12個の新規トピックおよび32名それぞれの属性に応じた原体験ストーリー・意見を永続化する。"""
    existing_topics = db.scalars(select(Topic)).all()
    existing_map = {t.title: t for t in existing_topics}
    user_by_handle = {u.handle: u for u in users}

    all_created_topics = []

    for spec in NEW_TOPICS_SPECS:
        topic = existing_map.get(spec["title"])
        if not topic:
            topic = Topic(
                title=spec["title"],
                description=spec["description"],
                created_by=users[0].id,
            )
            db.add(topic)
            db.flush()

            for axis_order, ax_spec in enumerate(spec["axes"]):
                axis = PositionAxis(
                    topic_id=topic.id,
                    name=ax_spec["name"],
                    order=axis_order,
                )
                db.add(axis)
                db.flush()
                for opt_label in ax_spec["options"]:
                    db.add(PositionOption(
                        axis_id=axis.id,
                        label=opt_label,
                    ))
            db.flush()

            for st_text in spec["statements"]:
                st_obj = Statement(
                    topic_id=topic.id,
                    body=st_text,
                    origin="seed",
                    author_id=users[0].id,
                )
                db.add(st_obj)
            db.flush()
        
        all_created_topics.append(topic)

    for topic in all_created_topics:
        stmts = db.scalars(
            select(Statement).where(Statement.topic_id == topic.id, Statement.status == "active")
        ).all()
        stmt_ids = [s.id for s in stmts]

        axes = db.scalars(
            select(PositionAxis).where(PositionAxis.topic_id == topic.id).order_by(PositionAxis.order.asc())
        ).all()

        has_votes = db.scalar(select(func.count(VoteEvent.id)).where(VoteEvent.topic_id == topic.id)) or 0
        if has_votes < 20:
            for u_idx, u in enumerate(users):
                pos_map = {}
                for ax_idx, axis in enumerate(axes):
                    opts = db.scalars(
                        select(PositionOption).where(PositionOption.axis_id == axis.id).order_by(PositionOption.id.asc())
                    ).all()
                    if opts:
                        chosen_opt = opts[(u_idx + ax_idx * 2) % len(opts)]
                        pos_map[axis.name] = chosen_opt.label
                        existing_pos = db.scalars(
                            select(UserTopicPosition).where(
                                UserTopicPosition.user_id == u.id,
                                UserTopicPosition.topic_id == topic.id,
                                UserTopicPosition.axis_id == axis.id
                            )
                        ).first()
                        if not existing_pos:
                            db.add(UserTopicPosition(
                                user_id=u.id,
                                topic_id=topic.id,
                                axis_id=axis.id,
                                option_id=chosen_opt.id
                            ))
                db.flush()

                for s_order, sid in enumerate(stmt_ids):
                    if s_order == 0:
                        val = 1 if (u_idx % 10 != 0) else -1
                    elif s_order in (1, 4):
                        val = 1 if (u_idx % 2 == 0) else -1
                    elif s_order == 2:
                        val = 1 if (u_idx % 3 != 0) else -1
                    else:
                        val = 1 if ((u_idx + s_order) % 4 != 0) else 0
                    
                    db.add(VoteEvent(
                        user_id=u.id,
                        statement_id=sid,
                        topic_id=topic.id,
                        value=val,
                        position_snapshot=pos_map,
                    ))
            db.flush()

    for contrib in PERSONA_CONTRIBUTIONS:
        handle = contrib["handle"]
        u = user_by_handle.get(handle)
        if not u:
            continue
        keyword = contrib["target_topic_keyword"]

        matched_topic = None
        for t in all_created_topics:
            if keyword in t.title or (t.description and keyword in t.description):
                matched_topic = t
                break
        if not matched_topic:
            continue

        u_snap = get_user_position_snapshot(db, u.id, matched_topic.id)

        opinion_text = contrib["opinion_statement"]
        existing_st = db.scalars(
            select(Statement).where(Statement.topic_id == matched_topic.id, Statement.body == opinion_text)
        ).first()
        if not existing_st:
            existing_st = Statement(
                topic_id=matched_topic.id,
                body=opinion_text,
                origin="user",
                author_id=u.id,
            )
            db.add(existing_st)
            db.flush()

            for other_u in users[:16]:
                if other_u.id != u.id:
                    o_snap = get_user_position_snapshot(db, other_u.id, matched_topic.id)
                    db.add(VoteEvent(
                        user_id=other_u.id,
                        statement_id=existing_st.id,
                        topic_id=matched_topic.id,
                        value=1,
                        position_snapshot=o_snap,
                    ))

        story_summary = contrib["story_summary"]
        existing_story = db.scalars(
            select(Story).where(Story.author_id == u.id, Story.summary == story_summary)
        ).first()
        if not existing_story:
            story = Story(
                author_id=u.id,
                topic_id=matched_topic.id,
                kind="present",
                summary=story_summary,
                body=contrib["story_body"],
                anonymization="none",
                position_snapshot=u_snap,
            )
            db.add(story)
            db.flush()

            db.add(StoryStatementLink(
                story_id=story.id,
                statement_id=existing_st.id,
                stance="supports",
            ))
            db.flush()

            for o_idx, other_u in enumerate(users[:8]):
                if other_u.id != u.id:
                    rx_kind = "resonate" if o_idx % 2 == 0 else "understand"
                    o_snap = get_user_position_snapshot(db, other_u.id, matched_topic.id)
                    db.add(StoryReaction(
                        user_id=other_u.id,
                        story_id=story.id,
                        kind=rx_kind,
                        position_snapshot=o_snap,
                    ))
            db.flush()

    db.commit()

    for t in all_created_topics:
        run_analysis(db, t.id)
    print("全12トピックのシードおよびペルソナストーリー反映、合意形成レポート編纂が完了しました。")


def ensure_seeded(db: Session) -> None:
    """起動時にトピック＆初期論点を整備し、32名×4日間のテスト実データを永続化する。"""
    topic = seed_initial_topic_and_statements(db)

    # ユーザーがすでに30名以上存在している場合でもトピック数が不足している場合は12トピックを補充
    user_count = db.scalar(select(func.count(User.id)).where(User.handle != "運営チーム")) or 0
    if user_count < 30:
        seed_4days_32personas(db, topic)
    else:
        topic_count = db.scalar(select(func.count(Topic.id))) or 0
        if topic_count < 13:
            users = db.scalars(select(User).where(User.handle != "運営チーム").order_by(User.id.asc())).all()
            seed_additional_12_topics(db, users)
