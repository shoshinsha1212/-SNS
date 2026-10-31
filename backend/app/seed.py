"""シード（起動時の初期データ）管理モジュール。

空のDBに、トピック・立場の軸・初期論点だけを入れる。参加者・票・体験談・レポートは作らない。
以前のバージョンが「実データ」として作っていた架空の参加者（ペルソナ32名）と、
それに由来する票・体験談・分析結果・レポートは、起動時に削除する。
"""

from __future__ import annotations

import secrets

from sqlalchemy import delete, select, update
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
from .seed_topics_data import NEW_TOPICS_SPECS

ADMIN_HANDLE = "運営チーム"

INITIAL_TOPIC = {
    "title": "教育現場での生成AI活用と行動原則",
    "description": (
        "学校や学習の場で生成AIをどう使い、どこに歯止めをかけるべきか。"
        "教員・生徒・保護者・開発者のそれぞれの現場のリアル（原体験）を持ち寄り、"
        "共通の原則と立場ごとの分岐点を整理します。"
    ),
    "axes": [
        {"name": "教育現場との関わり方", "options": ["教員・学校現場", "生徒・学生", "保護者", "AI開発・教育事業者", "当てはまらない"]},
        {"name": "日常での生成AIの利用頻度", "options": ["ほぼ毎日使う", "週に数回使う", "ほとんど使わない", "当てはまらない"]},
    ],
    "statements": [
        "生成AIが誤りや偏りを含みうることと、事実確認の方法をすべての児童・生徒に教えるべきだ",
        "児童・生徒の個人情報や成績・相談記録を、外部のAIの学習データとして送信してはならない",
        "障害や日本語の習熟度に応じた個別支援（読み上げ・やさしい日本語化など）にはAIを積極的に活用すべきだ",
        "教員の教材作成・校務文書・テスト作問の補助には、生成AIの利用を全面的に認めるべきだ",
        "読書感想文や探究レポートなどの宿題では、生成AIの使用を一律に禁止すべきだ",
        "授業で使うAIツールは、国や教育委員会が安全性を審査・認証したものだけに限定すべきだ",
        "生徒が自分の考えを整理する壁打ち相手として、授業中に自由にAIチャットを使えるようにすべきだ",
        "AIによる採点・評価補助を導入し、定期テストや小テストの採点業務を自動化すべきだ",
        "AIを使った箇所と対話履歴を提出時に明記することを条件として、レポート課題でのAI活用を認めるべきだ",
        "教員が最終確認し判断の根拠を説明できる場合に限り、校務や教材作成でのAI利用を認めるべきだ",
        "小学校の段階から、プログラミングと同様に生成AIとの対話技術を必修化すべきだ",
        "AIが悩みを聞くスクールカウンセリング補助を導入し、相談のハードルを下げるべきだ",
    ],
}

# 以前のシードが作っていた架空の参加者。削除対象の特定にだけ使う。
LEGACY_PERSONA_HANDLES = frozenset({
    "陸 (教育4年/実習生)", "奈央 (地方教育2年)", "健太 (社会3年/塾講師)", "美咲 (文1年/家庭教師)",
    "翔 (国際教養4年/TA)", "大輝 (理学4年/TA院進)", "萌花 (短大保育1年/実習)", "結菜 (看護2年/指導補佐)",
    "志保 (薬学3年/実習生)", "美優 (事務員/校務支援)", "健二 (公務員浪人/指導員)",
    "葵 (法学部2年)", "蓮 (経済3年)", "隼人 (理工2年)", "陽菜 (心理3年)", "栞 (文系3年)",
    "奏太 (音響専門2年)", "瑠美 (生活科学4年)", "玲奈 (メディア2年)", "莉子 (美容専門1年)",
    "俊介 (法学部3年/ROM)", "綾香 (通信制大1年)",
    "拓海 (情報3年/エンジニア)", "遥 (商学4年/EdTech内定)", "航希 (国際4年/学生起業)",
    "恭平 (経営3年/スタートアップ)", "渚 (UI/UXデザイナー)", "航 (工学部4年/地方国立)",
    "颯太 (インフラ若手社員)", "凛 (アパレル/EC企画)", "悠真 (製造業/データ担当)", "美羽 (Web制作フリーランス)",
})
_LEGACY_PERSONA_TRUST_LEVEL = 2


def _get_or_create_admin(db: Session) -> User:
    admin = db.scalars(select(User).where(User.handle == ADMIN_HANDLE)).first()
    if admin is None:
        admin = User(handle=ADMIN_HANDLE, token=secrets.token_hex(16), trust_level=9, is_synthetic=False)
        db.add(admin)
        db.flush()
    return admin


def _seed_topic(db: Session, admin: User, spec: dict) -> None:
    """同じタイトルのトピックがなければ、軸・選択肢・初期論点と一緒に作る。
    トピックはあるが論点が1件もない場合は、初期論点だけを補う。"""
    topic = db.scalars(select(Topic).where(Topic.title == spec["title"])).first()
    if topic is not None:
        if db.scalars(select(Statement.id).where(Statement.topic_id == topic.id)).first() is None:
            for body in spec["statements"]:
                db.add(Statement(topic_id=topic.id, author_id=admin.id, body=body, origin="seed", status="active"))
            db.flush()
        return
    topic = Topic(title=spec["title"], description=spec["description"], status="open", created_by=admin.id)
    db.add(topic)
    db.flush()
    for order, ax_spec in enumerate(spec["axes"]):
        axis = PositionAxis(topic_id=topic.id, name=ax_spec["name"], source="ai_proposed", order=order)
        db.add(axis)
        db.flush()
        for label in ax_spec["options"]:
            db.add(PositionOption(axis_id=axis.id, label=label))
    for body in spec["statements"]:
        db.add(Statement(topic_id=topic.id, author_id=admin.id, body=body, origin="seed", status="active"))
    db.flush()


def purge_legacy_personas(db: Session, admin: User) -> int:
    """以前のシードが作った架空の参加者と、その票・体験談・起案・分析結果・レポートを消す。

    端末IDを持たず、信頼度2で、ペルソナと同じ表示名のユーザーだけを対象にする。
    消したユーザー数を返す。
    """
    persona_ids = list(db.scalars(
        select(User.id).where(
            User.handle.in_(LEGACY_PERSONA_HANDLES),
            User.device_id.is_(None),
            User.trust_level == _LEGACY_PERSONA_TRUST_LEVEL,
        )
    ))
    if not persona_ids:
        return 0

    # 分析結果・レポート・貢献記録はすべて架空の票から計算されているので全部消す
    db.execute(delete(ReportCitation))
    db.execute(delete(Contribution))
    db.execute(delete(ReportVersion))
    db.execute(delete(StatementStats))
    db.execute(delete(GroupStats))
    db.execute(delete(UserProjection))
    db.execute(delete(AnalysisSnapshot))

    # 初期論点（origin=seed）は作成者がペルソナになっていても運営の論点として残す
    db.execute(
        update(Statement)
        .where(Statement.author_id.in_(persona_ids), Statement.origin == "seed")
        .values(author_id=admin.id)
    )
    # ペルソナが起案した論点と、それにぶら下がる票・紐づけ
    persona_stmt_ids = list(db.scalars(select(Statement.id).where(Statement.author_id.in_(persona_ids))))
    if persona_stmt_ids:
        db.execute(update(Statement).where(Statement.merged_into.in_(persona_stmt_ids)).values(merged_into=None))
        db.execute(delete(VoteEvent).where(VoteEvent.statement_id.in_(persona_stmt_ids)))
        db.execute(delete(StoryStatementLink).where(StoryStatementLink.statement_id.in_(persona_stmt_ids)))
        db.execute(delete(Statement).where(Statement.id.in_(persona_stmt_ids)))

    # ペルソナの体験談（他の人のリアクションごと）
    persona_story_ids = list(db.scalars(select(Story.id).where(Story.author_id.in_(persona_ids))))
    if persona_story_ids:
        db.execute(delete(StoryReaction).where(StoryReaction.story_id.in_(persona_story_ids)))
        db.execute(delete(StoryStatementLink).where(StoryStatementLink.story_id.in_(persona_story_ids)))
        db.execute(delete(Story).where(Story.id.in_(persona_story_ids)))

    # ペルソナ本人の行動
    db.execute(delete(VoteEvent).where(VoteEvent.user_id.in_(persona_ids)))
    db.execute(delete(StoryReaction).where(StoryReaction.user_id.in_(persona_ids)))
    db.execute(delete(UserTopicPosition).where(UserTopicPosition.user_id.in_(persona_ids)))
    db.execute(delete(UserAttribute).where(UserAttribute.user_id.in_(persona_ids)))
    db.execute(update(Topic).where(Topic.created_by.in_(persona_ids)).values(created_by=admin.id))
    db.execute(delete(User).where(User.id.in_(persona_ids)))

    # 運営が入れた初期論点に付いていた「参加者の投稿」などの出自ラベルは事実ではないので戻す
    db.execute(
        update(Statement)
        .where(Statement.author_id == admin.id, Statement.origin != "seed")
        .values(origin="seed")
    )
    return len(persona_ids)


def ensure_seeded(db: Session) -> None:
    """起動時に呼ぶ。架空データを消し、足りないトピックと初期論点だけを補う。"""
    admin = _get_or_create_admin(db)
    removed = purge_legacy_personas(db, admin)
    if removed:
        print(f"以前のシードが作った架空の参加者 {removed} 名と関連データを削除しました。")
    _seed_topic(db, admin, INITIAL_TOPIC)
    for spec in NEW_TOPICS_SPECS:
        _seed_topic(db, admin, spec)
    db.commit()
