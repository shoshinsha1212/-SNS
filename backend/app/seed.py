"""シードおよびテストデータ管理モジュール。

本番・テストユーザー運用向けに、架空の参加者（80名）と架空の投票・レポートを完全削除し、
トピックと初期論点（12問）のみが登録されたクリーンな初期状態を維持します。
"""

from __future__ import annotations

import os
import secrets
from typing import Any

import numpy as np
from sqlalchemy import select, text
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
)
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


def cleanup_synthetic_data(db: Session) -> dict[str, int]:
    """架空のテスト参加者（80名）と付随する投票・ストーリー・レポートを完全削除し、
    本物の参加者がゼロから投票・投稿できる状態にする。
    """
    try:
        db.execute(text("PRAGMA foreign_keys = OFF;"))
    except Exception:
        pass

    # 運営ユーザーを確保（初期論点の投稿者として紐付け）
    admin = db.scalars(select(User).where(User.handle == "運営チーム")).first()
    if not admin:
        admin = User(handle="運営チーム", token=secrets.token_hex(16), trust_level=9, is_synthetic=False)
        db.add(admin)
        db.flush()

    # トピックと初期論点の author/created_by を運営チームに退避
    for t in db.scalars(select(Topic)).all():
        t.created_by = admin.id
    for st in db.scalars(select(Statement)).all():
        st.author_id = admin.id
    db.flush()

    # 架空ユーザー（is_synthetic == True または "参加者" handle）のID一覧を取得
    synthetic_users = list(
        db.scalars(
            select(User).where((User.is_synthetic == True) | (User.handle.like("%参加者%")))
        ).all()
    )
    synthetic_user_ids = [u.id for u in synthetic_users]

    deleted_counts: dict[str, int] = {
        "users": len(synthetic_user_ids),
        "votes": 0,
        "stories": 0,
    }

    # 1. レポート関連（Citation -> Contribution -> ReportVersion）
    db.query(ReportCitation).delete(synchronize_session=False)
    db.query(Contribution).delete(synchronize_session=False)
    db.query(ReportVersion).delete(synchronize_session=False)

    # 2. 分析スナップショット関連（UserProjection, GroupStats, StatementStats -> AnalysisSnapshot）
    db.query(UserProjection).delete(synchronize_session=False)
    db.query(GroupStats).delete(synchronize_session=False)
    db.query(StatementStats).delete(synchronize_session=False)
    db.query(AnalysisSnapshot).delete(synchronize_session=False)

    # 3. ストーリー・リアクション関連
    if synthetic_user_ids:
        db.query(StoryReaction).filter(StoryReaction.user_id.in_(synthetic_user_ids)).delete(synchronize_session=False)

        synthetic_story_ids = list(
            db.scalars(select(Story.id).where(Story.author_id.in_(synthetic_user_ids))).all()
        )
        if synthetic_story_ids:
            deleted_counts["stories"] = len(synthetic_story_ids)
            db.query(StoryReaction).filter(
                StoryReaction.story_id.in_(synthetic_story_ids)
            ).delete(synchronize_session=False)
            db.query(StoryStatementLink).filter(
                StoryStatementLink.story_id.in_(synthetic_story_ids)
            ).delete(synchronize_session=False)
            db.query(Story).filter(Story.id.in_(synthetic_story_ids)).delete(synchronize_session=False)

        # 4. 投票データ
        del_votes = db.query(VoteEvent).filter(
            VoteEvent.user_id.in_(synthetic_user_ids)
        ).delete(synchronize_session=False)
        deleted_counts["votes"] = del_votes

        # 5. 属性・立場
        db.query(UserAttribute).filter(
            UserAttribute.user_id.in_(synthetic_user_ids)
        ).delete(synchronize_session=False)
        db.query(UserTopicPosition).filter(
            UserTopicPosition.user_id.in_(synthetic_user_ids)
        ).delete(synchronize_session=False)

        # 6. 架空ユーザー本体
        db.query(User).filter(User.id.in_(synthetic_user_ids)).delete(synchronize_session=False)

    db.commit()

    try:
        db.execute(text("PRAGMA foreign_keys = ON;"))
    except Exception:
        pass

    return deleted_counts


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


def ensure_seeded(db: Session) -> None:
    """起動時にトピック＆初期論点を整備し、架空参加者データを確実にクリーンアップする。"""
    topic = seed_initial_topic_and_statements(db)

    # 架空ユーザー80名のクリーンアップ（テストユーザー実地検証用）
    cleanup_synthetic_data(db)

    # 環境変数 SEED_SYNTHETIC=1 が明示されている場合のみデモデータを投入
    if os.environ.get("SEED_SYNTHETIC", "").lower() in ("1", "true"):
        _seed_synthetic_demo_data(db, topic)


def _seed_synthetic_demo_data(db: Session, topic: Topic) -> None:
    """（必要時のみ）架空の参加者80名とデモ投票・ストーリー・レポートを投入する開発・テスト用ヘルパー。"""
    rng = np.random.default_rng(2026)
    axes = list(db.scalars(select(PositionAxis).where(PositionAxis.topic_id == topic.id).order_by(PositionAxis.order)).all())
    if len(axes) < 2:
        return
    ax1, ax2 = axes[0], axes[1]
    opts1 = {o.label: o for o in db.scalars(select(PositionOption).where(PositionOption.axis_id == ax1.id)).all()}
    opts2 = {o.label: o for o in db.scalars(select(PositionOption).where(PositionOption.axis_id == ax2.id)).all()}

    pos_labels = ["教員・学校現場", "生徒・学生", "保護者", "AI開発・教育事業者"]
    freq_labels = ["ほぼ毎日使う", "週に数回使う", "ほとんど使わない"]
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
            if p_label in opts1:
                db.add(UserTopicPosition(user_id=u.id, topic_id=topic.id, axis_id=ax1.id, option_id=opts1[p_label].id))
            f_lbl = freq_labels[(p_idx + i) % len(freq_labels)]
            if f_lbl in opts2:
                db.add(UserTopicPosition(user_id=u.id, topic_id=topic.id, axis_id=ax2.id, option_id=opts2[f_lbl].id))
            users_by_pos[p_label].append(u)
    db.flush()

    statements = list(db.scalars(select(Statement).where(Statement.topic_id == topic.id)).all())
    snap_by_user = {u.id: get_user_position_snapshot(db, u.id, topic.id) for p_label in pos_labels for u in users_by_pos[p_label]}

    for s_idx, (_, origin, probs) in enumerate(INITIAL_STATEMENTS):
        if s_idx >= len(statements):
            break
        st = statements[s_idx]
        st.origin = origin
        for p_idx, p_label in enumerate(pos_labels):
            p_agree = probs[p_idx]
            for u_idx, u in enumerate(users_by_pos[p_label]):
                if s_idx in (3, 4, 5, 6) and u_idx == 19:
                    val = -1 if p_agree >= 0.5 else 1
                else:
                    val = 1 if rng.random() < p_agree else -1
                db.add(VoteEvent(user_id=u.id, statement_id=st.id, topic_id=topic.id, value=val, position_snapshot=snap_by_user[u.id]))
    db.flush()

    # 体験談（ストーリー）
    story_specs = [
        (3, users_by_pos["教員・学校現場"][0], "present", "supports", "プリント作成と保護者文書のたたき台をAIで作ることで、放課後に生徒と向き合う時間が週4時間増えました。", "中学校で担任をしています。AIにたたき台を作らせて自分で手直しするようになってから、放課後に不登校気味の生徒とゆっくり話す時間が週に4時間ほど確保できるようになりました。"),
        (3, users_by_pos["保護者"][0], "future", "opposes", "先生からの所見やコメントまでAIの定型文になったら、子どもを本当に見てくれているのか信頼できなくなる懸念があります。", "小学生の子どもを持つ保護者です。業務が大変なのは理解しますが、通知表の所見や連絡帳のやりとりまでAIで作られたら不安です。"),
        (3, users_by_pos["保護者"][19], "past", "supports", "担任の先生が過労で休職した経験から、事務作業はAIに任せて先生の健康と授業の質を守るべきだと考えるようになりました。", "昨年、子どもの担任の先生が長時間労働で休職してしまった経験があります。事務や下準備こそAIに任せるべきだと思います。"),
    ]
    for s_idx, author, kind, stance, summary, body in story_specs:
        st_obj = Story(author_id=author.id, topic_id=topic.id, kind=kind, body=body, summary=summary, anonymization="none", position_snapshot=snap_by_user[author.id])
        db.add(st_obj)
        db.flush()
        db.add(StoryStatementLink(story_id=st_obj.id, statement_id=statements[s_idx].id, stance=stance))
        for p_label in pos_labels:
            for u in users_by_pos[p_label][:2]:
                if u.id != author.id:
                    db.add(StoryReaction(user_id=u.id, story_id=st_obj.id, kind="resonate", position_snapshot=snap_by_user[u.id]))

    db.commit()
    run_analysis(db, topic.id)
