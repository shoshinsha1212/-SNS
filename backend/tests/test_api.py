"""API を通した参加者の流れ・価値観マップ・通報・計測の検証。"""

from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ADMIN_KEY"] = "test-admin"

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, reset_db
from app.main import FLAG_HIDE_THRESHOLD, app
from app.seed import ensure_seeded
from app.values import AXIS_KEYS, MAP_COMPLETE_TOPICS, SEED_TOPICS

ADMIN = {"X-Admin-Key": "test-admin"}


@pytest.fixture()
def client():
    reset_db()
    with SessionLocal() as db:
        ensure_seeded(db)
    with TestClient(app) as c:
        yield c


def new_user(c: TestClient) -> dict:
    tok = c.post("/api/users").json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def answer_topic(c, h, topic_id, value_for=lambda i: 1, reason=None):
    stmts = c.get(f"/api/topics/{topic_id}", headers=h).json()["statements"]
    last = None
    for i, s in enumerate(stmts):
        last = c.post(f"/api/statements/{s['id']}/vote", json={"value": value_for(i), "reason": reason}, headers=h)
        assert last.status_code == 200, last.text
    return last.json()


def test_seed_has_topics_but_no_participants(client):
    topics = client.get("/api/topics").json()
    assert len(topics) == len(SEED_TOPICS)
    assert all(t["n_participants"] == 0 for t in topics)
    for spec in SEED_TOPICS:
        for _, axis, direction in spec["statements"]:
            assert axis is None or (axis in AXIS_KEYS and direction in (1, -1))


def test_answer_results_and_opposite_side(client):
    topic_id = client.get("/api/topics").json()[0]["id"]
    # 6人が賛成、1人（私）が1問目だけ反対
    for _ in range(6):
        h = new_user(client)
        answer_topic(client, h, topic_id, reason="自分の経験からそう思う")
    me = new_user(client)
    res = answer_topic(client, me, topic_id, value_for=lambda i: -1 if i == 0 else 1)
    assert res["topic_completed_now"] is True
    assert res["completed_topics"] == 1

    r = client.get(f"/api/topics/{topic_id}/results", headers=me).json()
    assert r["n_participants"] == 7
    first = r["statements"][0]
    assert first["my_vote"] == -1
    assert first["same_rate"] == pytest.approx(1 / 7)
    assert first["label"] == "consensus_agree"
    # 反対側（賛成した人）の理由が見える
    assert first["reasons"]["agree"] and first["reasons"]["agree"][0]["text"] == "自分の経験からそう思う"
    assert r["summary"]["most_minority"]["id"] == first["id"]
    groups = {g["key"]: g for g in first["groups"]}
    assert groups["other"]["agree"] == 6 and groups["other"]["disagree"] == 1
    assert groups["student"]["agree"] == 0
    assert r["summary"]["n_majority"] == len(r["statements"]) - 1


def test_value_map_partial_then_complete(client):
    h = new_user(client)
    topics = client.get("/api/topics").json()
    answer_topic(client, h, topics[0]["id"])
    m = client.get("/api/me/map", headers=h).json()
    assert m["complete"] is False and m["completed_topics"] == 1
    sol = next(a for a in m["axes"] if a["key"] == "solidarity")
    # 学費の議題：支え合い寄り2問・自己責任寄り1問に全部賛成 → (1+1-1)/3
    assert sol["score"] == pytest.approx(1 / 3)
    assert len(sol["basis"]) == 3
    assert m["type_name"]

    last = None
    for t in topics[1:MAP_COMPLETE_TOPICS]:
        last = answer_topic(client, h, t["id"])
    assert last["map_completed_now"] is True
    m = client.get("/api/me/map", headers=h).json()
    assert m["complete"] is True
    assert sum(sum(a["histogram"]) for a in m["axes"]) >= 1


def test_user_topic_story_and_flag_hides(client):
    author = new_user(client)
    bad = client.post("/api/topics", json={"title": "短い", "statements": []}, headers=author)
    assert bad.status_code == 422
    tid = client.post("/api/topics", json={
        "title": "学食の値上げ",
        "statements": [
            {"body": "学食の値上げはやむを得ない", "axis_key": "solidarity", "direction": -1},
            {"body": "学食は大学が補助して安く保つべきだ"},
            {"body": "値上げするなら量を増やしてほしい"},
        ],
    }, headers=author).json()["id"]
    t = client.get(f"/api/topics/{tid}").json()
    sid = t["statements"][0]["id"]
    added = client.post(f"/api/topics/{tid}/statements", json={"body": "学食のメニューを学生が決められるようにすべきだ"},
                        headers=author)
    assert added.status_code == 200
    client.post(f"/api/statements/{sid}/vote", json={"value": 1}, headers=author)
    story = client.post(f"/api/statements/{sid}/stories", json={"body": "一人暮らしで毎日学食に通っていて、値上げは痛かった。"},
                        headers=author).json()
    assert story["stance"] == 1

    for _ in range(FLAG_HIDE_THRESHOLD):
        r = client.post("/api/flags", json={"target_type": "story", "target_id": story["id"]}, headers=new_user(client))
    assert r.json()["hidden"] is True
    res = client.get(f"/api/topics/{tid}/results").json()
    assert res["statements"][0]["n_stories"] == 0

    flags = client.get("/api/admin/flags", headers=ADMIN).json()
    assert flags[0]["count"] == FLAG_HIDE_THRESHOLD and flags[0]["hidden"] is True
    client.post("/api/admin/moderate", json={"target_type": "story", "target_id": story["id"], "action": "show"},
                headers=ADMIN)
    assert client.get(f"/api/topics/{tid}/results").json()["statements"][0]["n_stories"] == 1


def test_metrics_funnel_and_admin_guard(client):
    assert client.get("/api/admin/metrics").status_code == 403
    topics = client.get("/api/topics").json()
    h = new_user(client)
    client.post("/api/events", json={"name": "visit"}, headers=h)
    client.post("/api/events", json={"name": "topic_view", "topic_id": topics[0]["id"]}, headers=h)
    assert client.post("/api/events", json={"name": "topic_complete"}, headers=h).status_code == 400
    answer_topic(client, h, topics[0]["id"])
    client.post("/api/events", json={"name": "result_view", "topic_id": topics[0]["id"]}, headers=h)
    # 結果を見ずに2議題目へ進んだ人は、漏斗（前の段階を全部通った人）には入らない
    skipper = new_user(client)
    client.post("/api/events", json={"name": "visit"}, headers=skipper)
    answer_topic(client, skipper, topics[2]["id"])
    first =client.get(f"/api/topics/{topics[1]['id']}", headers=h).json()["statements"][0]
    client.post(f"/api/statements/{first['id']}/vote", json={"value": 0}, headers=h)
    client.post(f"/api/topics/{topics[0]['id']}/understanding", json={"score": 4}, headers=h)

    m = client.get("/api/admin/metrics", headers=ADMIN).json()
    f = {s["key"]: s["users"] for s in m["funnel"]}
    raw = {s["key"]: s["raw"] for s in m["funnel"]}
    assert f["visit"] == 2 and f["topic_view"] == 1 and f["first_vote"] == 1 and f["complete1"] == 1
    assert raw["first_vote"] == 2 and raw["complete1"] == 2
    assert f["start2"] == 1 and f["complete2"] == 0
    t1 = next(t for t in m["topics"] if t["id"] == topics[1]["id"])
    assert t1["dropoff"] == [{"answered": 1, "users": 1}]
    assert m["understanding"]["avg"] == 4


def test_admin_axis_tagging(client):
    stmts = client.get("/api/admin/statements", headers=ADMIN).json()
    untagged = next(s for s in stmts if s["axis_key"] is None)
    r = client.patch(f"/api/admin/statements/{untagged['id']}", json={"axis_key": "change", "direction": 1},
                     headers=ADMIN)
    assert r.json()["axis_key"] == "change"
    assert client.patch(f"/api/admin/statements/{untagged['id']}", json={"axis_key": "change"},
                        headers=ADMIN).status_code == 422


def test_spa_route_does_not_serve_files_outside_dist(client):
    import app.main as main_mod

    if not main_mod._frontend_dist.exists():
        pytest.skip("frontend/dist が無いため SPA ルートが登録されていない")
    for path in ("/..%2F..%2Fbackend%2Fpyproject.toml", "/%2e%2e/%2e%2e/backend/pyproject.toml"):
        assert "[project]" not in client.get(path).text
