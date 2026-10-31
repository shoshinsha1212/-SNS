"""アルゴリズムとAPIエンドポイントの検証テスト。"""

from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import numpy as np
from sqlalchemy import select
from app.models import Topic, User

from app.analysis.dependence import position_dependence
from app.analysis.params import DEFAULT_PARAMS
from app.analysis.stats import GroupCount, benjamini_hochberg, gap, gic, independence_p
from app.db import SessionLocal, init_db
from app.main import (
    CreateStatementReq,
    CreateTopicReq,
    CreateUserReq,
    PostStoryReq,
    PutPositionsReq,
    ReactionReq,
    StoryIn,
    SuggestAxesReq,
    VoteReq,
    api_analyze_topic,
    api_convert_complaint,
    api_create_topic,
    api_create_user,
    api_generate_bridges,
    api_get_contributions,
    api_get_diagnosis,
    api_get_latest_report,
    api_get_map,
    api_get_statement,
    api_get_topic,
    api_list_statements,
    api_list_topics,
    api_meta,
    api_next_statement,
    api_post_statement,
    api_post_story,
    api_put_positions,
    api_react_story,
    api_suggest_axes,
    api_vote_statement,
    ConvertReq,
)
from app.models import User
from app.seed import ensure_seeded


def test_algorithm_metrics():
    """02_アルゴリズム.md の立場依存度・ギャップ・検定が意図通り動くか検証。"""
    rng = np.random.default_rng(0)

    # 1. 立場で明確に分かれているケース（A群: 18賛成/2反対, B群: 2賛成/18反対）
    groups_div = {
        "立場A": GroupCount(n_agree=18, n_disagree=2),
        "立場B": GroupCount(n_agree=2, n_disagree=18),
    }
    g_val = gap(groups_div, DEFAULT_PARAMS)
    p_val = independence_p(groups_div, DEFAULT_PARAMS, rng)
    assert g_val is not None and g_val > 0.60
    assert p_val is not None and p_val < 0.001

    rows = [{"axis:1": "立場A"} for _ in range(20)] + [{"axis:1": "立場B"} for _ in range(20)]
    y = [1] * 18 + [0] * 2 + [1] * 2 + [0] * 18
    pd_val = position_dependence(rows, y, ["axis:1"], DEFAULT_PARAMS)
    assert pd_val is not None and pd_val > 0.25

    # 2. 立場と無関係なケース（両方とも 10賛成/10反対）
    groups_ind = {
        "立場A": GroupCount(n_agree=10, n_disagree=10),
        "立場B": GroupCount(n_agree=10, n_disagree=10),
    }
    assert gap(groups_ind, DEFAULT_PARAMS) == 0.0
    p_ind = independence_p(groups_ind, DEFAULT_PARAMS, rng)
    assert p_ind is not None and p_ind > 0.5
    y_ind = [1, 0] * 20
    pd_ind = position_dependence(rows, y_ind, ["axis:1"], DEFAULT_PARAMS)
    assert pd_ind is not None and pd_ind < 0.05

    # 3. 共通合意の GIC と Benjamini-Hochberg
    g_consensus = [GroupCount(n_agree=19, n_disagree=1), GroupCount(n_agree=18, n_disagree=2)]
    assert (gic(g_consensus) or 0) > 0.70
    qmap = benjamini_hochberg({1: 0.0001, 2: 0.80})
    assert qmap[1] < 0.01 and qmap[2] > 0.5


def _add_test_voters(db, topic_id: int, n: int = 30) -> None:
    """テスト用の投票者（is_synthetic=True）を作る。第1軸の2つの立場で半々に分け、
    最初の3問は全員賛成（共通原則）、4・5問目は立場で賛否が割れる（分岐点）ようにする。"""
    td = api_get_topic(topic_id, user=None, db=db)
    axis = td["axes"][0]
    for i in range(n):
        u = User(handle=f"テスト投票者{i}", token=f"test-voter-{topic_id}-{i}", is_synthetic=True)
        db.add(u)
        db.commit()
        side = i % 2
        api_put_positions(
            topic_id,
            PutPositionsReq(positions={str(axis["id"]): axis["options"][side]["id"]}),
            user=u,
            db=db,
        )
        stmts = api_list_statements(topic_id, user=u, db=db)
        for idx, s in enumerate(stmts):
            if idx < 3:
                value = 1
            elif idx < 5:
                value = 1 if side == 0 else -1
            else:
                value = 1 if (i + idx) % 3 else -1
            api_vote_statement(s["id"], VoteReq(value=value), user=u, db=db)


def test_seed_creates_no_fake_participants_and_purges_legacy_personas():
    """シードは架空の参加者・票・レポートを作らず、以前のペルソナは起動時に消えること。"""
    from app.models import Story, VoteEvent
    from app.seed import LEGACY_PERSONA_HANDLES

    init_db()
    with SessionLocal() as db:
        ensure_seeded(db)
        topics = api_list_topics(db=db)
        assert len(topics) == 13
        assert all(t["n_participants"] == 0 for t in topics)
        assert all(t["report_version"] is None for t in topics)

        # 以前のバージョンが作ったペルソナを再現し、実在の参加者と一緒に置く
        topic_id = topics[0]["id"]
        stmt_id = api_list_statements(topic_id, user=None, db=db)[0]["id"]
        persona = User(handle=sorted(LEGACY_PERSONA_HANDLES)[0], token="legacy-persona", trust_level=2)
        real = User(handle=sorted(LEGACY_PERSONA_HANDLES)[0], token="real-same-name", device_id="dev-1")
        db.add_all([persona, real])
        db.commit()
        api_vote_statement(stmt_id, VoteReq(value=1), user=persona, db=db)
        api_vote_statement(stmt_id, VoteReq(value=-1), user=real, db=db)
        db.add(Story(author_id=persona.id, topic_id=topic_id, body="架空の体験談"))
        from app.models import Statement

        seed_by_persona = Statement(topic_id=topic_id, author_id=persona.id, body="初期論点", origin="seed")
        proposed_by_persona = Statement(topic_id=topic_id, author_id=persona.id, body="架空の起案", origin="user")
        db.add_all([seed_by_persona, proposed_by_persona])
        db.commit()

        ensure_seeded(db)
        assert db.get(Statement, seed_by_persona.id) is not None
        assert db.get(Statement, proposed_by_persona.id) is None
        assert db.get(User, persona.id) is None
        assert db.get(User, real.id) is not None
        assert db.scalars(select(VoteEvent).where(VoteEvent.user_id == persona.id)).first() is None
        assert db.scalars(select(VoteEvent).where(VoteEvent.user_id == real.id)).first() is not None
        assert db.scalars(select(Story).where(Story.author_id == persona.id)).first() is None


def test_full_api_flow():
    """シードデータからユーザー登録・立場選択・投票・診断・意見マップ・成果物生成までの一連の流れを検証。"""
    init_db()
    with SessionLocal() as db:
        ensure_seeded(db)

        # 1. メタ情報とトピック一覧
        meta = api_meta()
        assert len(meta["attributes"]) >= 2

        topics = api_list_topics(db=db)
        assert len(topics) >= 1
        topic_id = topics[0]["id"]

        _add_test_voters(db, topic_id)
        api_analyze_topic(topic_id, db=db)
        topics = api_list_topics(db=db)
        assert topics[0]["n_participants"] >= 30
        assert topics[0]["report_version"] is not None

        # 2. ユーザー登録
        reg = api_create_user(
            CreateUserReq(handle="テスト参加者", attributes={"age_band": "30代・40代"}),
            db=db,
        )
        user = db.get(User, reg["user"]["id"])
        assert user is not None

        # 3. トピック詳細と立場選択
        td = api_get_topic(topic_id, user=user, db=db)
        first_axis = td["axes"][0]
        first_opt = first_axis["options"][0]
        td_after = api_put_positions(
            topic_id,
            PutPositionsReq(positions={str(first_axis["id"]): first_opt["id"]}),
            user=user,
            db=db,
        )
        assert td_after["my_positions"][str(first_axis["id"])] == first_opt["id"]

        # 4. 原則一覧の分類結果（共通原則・分岐点・条件付き合意案・価値観分岐がすべて存在すること）
        stmts = api_list_statements(topic_id, user=user, db=db)
        sections = {s["section"] for s in stmts}
        assert "consensus" in sections
        assert "divergence" in sections

        # 5. 全原則に投票して個人診断とマップを確認
        nxt = api_next_statement(topic_id, user=user, db=db)
        assert nxt["statement"] is not None
        for s in stmts:
            v_res = api_vote_statement(s["id"], VoteReq(value=1), user=user, db=db)
            assert v_res["my_vote"] == 1

        api_analyze_topic(topic_id, db=db)

        diag = api_get_diagnosis(topic_id, user=user, db=db)
        assert diag["ready"] is True
        assert diag["typicality"] is not None

        map_data = api_get_map(topic_id, user=user, db=db)
        assert map_data["available"] is True
        assert len(map_data["points"]) >= 30
        assert any(p["is_me"] for p in map_data["points"])

        # 6. 不満から原則への変換（P1）、投稿、体験談と反応、条件付き合意案の生成（P5）
        conv = api_convert_complaint(
            topic_id,
            ConvertReq(text="家庭学習でAIをどう使えばいいか基準がなくて困っています。去年も宿題の扱いで迷いました。"),
            db=db,
        )
        assert len(conv["principles"]) >= 1

        post_res = api_post_statement(
            topic_id,
            CreateStatementReq(
                text=conv["principles"][0]["text"],
                origin="ai_from_complaint",
                story=StoryIn(kind="past", body="去年、宿題でAIをどこまで使ってよいか分からず困った経験があります。"),
            ),
            user=user,
            db=db,
        )
        assert post_res["statement"] is not None
        new_sid = post_res["statement"]["id"]

        st_detail = api_get_statement(new_sid, user=user, db=db)
        assert len(st_detail["stories"]["supports"]) == 1
        story_id = st_detail["stories"]["supports"][0]["id"]

        reac = api_react_story(story_id, ReactionReq(kind="understand"), user=user, db=db)
        assert reac["reactions"]["understand"] == 1

        div_sid = next(s["id"] for s in stmts if s["section"] == "divergence")
        br_res = api_generate_bridges(div_sid, user=user, db=db)
        assert len(br_res["created"]) >= 1

        # 7. 新規トピック作成と成果物・貢献の取得
        sug = api_suggest_axes(SuggestAxesReq(title="クリエイティブ制作とAI"))
        assert len(sug["axes"]) >= 1
        new_topic = api_create_topic(
            CreateTopicReq(title="新しいテストトピック", description="説明"),
            user=user,
            db=db,
        )
        assert new_topic["id"] > topic_id

        # 分岐点に体験談を付けてから再編纂すると、レポートに体験談の引用 [T:] が入る
        api_post_story(
            div_sid,
            PostStoryReq(kind="present", body="授業で実際に困った経験があり、この論点には賛成です。", stance="supports"),
            user=user,
            db=db,
        )
        api_analyze_topic(topic_id, db=db)
        rep = api_get_latest_report(topic_id, db=db)
        assert "[S:" in rep["body_md"]
        assert "[T:" in rep["body_md"]

        contribs = api_get_contributions(user=user, db=db)
        assert isinstance(contribs, list)


def test_spa_route_does_not_serve_files_outside_dist():
    """`..` を含むパスで dist の外（pyproject.toml や DB）が読めないこと。"""
    import app.main as main_mod
    from fastapi.testclient import TestClient

    if not main_mod._frontend_dist.exists():
        import pytest

        pytest.skip("frontend/dist が無いため SPA ルートが登録されていない")
    client = TestClient(main_mod.app)
    for path in ("/..%2F..%2Fbackend%2Fpyproject.toml", "/%2e%2e/%2e%2e/backend/pyproject.toml"):
        res = client.get(path)
        assert "[project]" not in res.text
