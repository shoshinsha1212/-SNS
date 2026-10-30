"""分析・集計サービス（DB と app/analysis の橋渡し）。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analysis.clustering import opinion_map
from ..analysis.dependence import position_dependence
from ..analysis.params import DEFAULT_PARAMS, Params
from ..analysis.stats import (
    GroupCount,
    benjamini_hochberg,
    gap,
    gic,
    independence_p,
    normalized_mutual_info,
    smoothed_rate,
    surprise_bits,
)
from ..models import (
    AnalysisSnapshot,
    Contribution,
    GroupStats,
    PositionOption,
    ReportCitation,
    ReportVersion,
    Statement,
    StatementStats,
    Story,
    StoryReaction,
    StoryStatementLink,
    Topic,
    UserAttribute,
    UserProjection,
    UserTopicPosition,
    VoteEvent,
)
from .ai_service import compile_report

META_ATTRIBUTES: list[dict[str, Any]] = [
    {
        "key": "age_band",
        "label": "年代",
        "options": ["10代・20代", "30代・40代", "50代以上"],
    },
    {
        "key": "role_style",
        "label": "普段の役割",
        "options": ["現場・実務中心", "企画・専門職", "管理・運営・経営", "学生・市民・その他"],
    },
]


def get_dimensions_for_topic(topic: Topic) -> list[tuple[str, str, list[str]]]:
    """(dimension_key, dimension_label, option_labels) の一覧を返す。"""
    dims: list[tuple[str, str, list[str]]] = []
    for ax in topic.axes:
        dims.append((f"axis:{ax.id}", ax.name, [opt.label for opt in ax.options]))
    for attr in META_ATTRIBUTES:
        dims.append((f"attr:{attr['key']}", attr["label"], list(attr["options"])))
    return dims


def get_user_position_snapshot(db: Session, user_id: int, topic_id: int) -> dict[str, str]:
    """現在のユーザーの立場（トピック固有の立場＋基本属性）を辞書にして返す。"""
    snap: dict[str, str] = {}
    rows = db.scalars(
        select(UserTopicPosition).where(
            UserTopicPosition.user_id == user_id,
            UserTopicPosition.topic_id == topic_id,
            UserTopicPosition.valid_to.is_(None),
        )
    ).all()
    if rows:
        opt_ids = [r.option_id for r in rows]
        opts = {
            o.id: o.label
            for o in db.scalars(select(PositionOption).where(PositionOption.id.in_(opt_ids))).all()
        }
        for r in rows:
            if r.option_id in opts:
                snap[f"axis:{r.axis_id}"] = opts[r.option_id]

    attrs = db.scalars(select(UserAttribute).where(UserAttribute.user_id == user_id)).all()
    for a in attrs:
        if a.value:
            snap[f"attr:{a.key}"] = a.value
    return snap


def get_latest_votes(db: Session, topic_id: int) -> dict[tuple[int, int], VoteEvent]:
    """(user_id, statement_id) ごとの最新 VoteEvent を返す。"""
    events = db.scalars(
        select(VoteEvent)
        .where(VoteEvent.topic_id == topic_id)
        .order_by(VoteEvent.created_at.asc(), VoteEvent.id.asc())
    ).all()
    latest: dict[tuple[int, int], VoteEvent] = {}
    for ev in events:
        latest[(ev.user_id, ev.statement_id)] = ev
    return latest


def _group_counts_for_statement(
    statement_id: int,
    dims: list[tuple[str, str, list[str]]],
    latest_votes: dict[tuple[int, int], VoteEvent],
) -> dict[str, dict[str, GroupCount]]:
    """dimension -> group_label -> GroupCount を集計する。"""
    result: dict[str, dict[str, GroupCount]] = {
        d_key: {opt: GroupCount() for opt in opts} for d_key, _, opts in dims
    }
    for (_, sid), ev in latest_votes.items():
        if sid != statement_id:
            continue
        snap = ev.position_snapshot or {}
        for d_key, _, _ in dims:
            grp = snap.get(d_key)
            if not grp:
                continue
            if grp not in result[d_key]:
                result[d_key][grp] = GroupCount()
            gc = result[d_key][grp]
            if ev.value == 1:
                gc.n_agree += 1
            elif ev.value == -1:
                gc.n_disagree += 1
            else:
                gc.n_pass += 1
    return result


def compute_by_position(
    topic: Topic,
    statement_id: int,
    latest_votes: dict[tuple[int, int], VoteEvent],
    params: Params = DEFAULT_PARAMS,
) -> list[dict[str, Any]]:
    """原則1件に対する立場別賛成率（最小人数ルール適用済み）を返す。"""
    dims = get_dimensions_for_topic(topic)
    counts_by_dim = _group_counts_for_statement(statement_id, dims, latest_votes)
    out: list[dict[str, Any]] = []
    for d_key, d_label, opts in dims:
        dim_map = counts_by_dim.get(d_key, {})
        ordered_keys = list(opts) + [k for k in dim_map if k not in opts]
        for g_label in ordered_keys:
            if g_label == "当てはまらない":
                continue
            gc = dim_map.get(g_label, GroupCount())
            if gc.n_seen == 0 and g_label not in opts:
                continue
            hidden = gc.n_ad < params.min_group_n
            rate = None if hidden else round(smoothed_rate(gc, params), 4)
            out.append(
                {
                    "dimension": d_key,
                    "dimension_label": d_label,
                    "group": g_label,
                    "group_label": g_label,
                    "n": gc.n_ad,
                    "agree_rate": rate,
                    "hidden": hidden,
                }
            )
    return out


def is_boundary_voter(
    topic: Topic,
    statement_id: int,
    author_id: int,
    author_snapshot: dict[str, str],
    latest_votes: dict[tuple[int, int], VoteEvent],
    params: Params = DEFAULT_PARAMS,
) -> bool:
    """2.7 境界人の判定：自分の立場の多数派と逆（25%以下）で、他の立場の多数派と一致する票を入れた人。"""
    ev = latest_votes.get((author_id, statement_id))
    if ev is None or ev.value not in (1, -1):
        return False
    dims = get_dimensions_for_topic(topic)
    if not dims:
        return False
    primary_dim = dims[0][0]
    my_group = (ev.position_snapshot or author_snapshot or {}).get(primary_dim)
    if not my_group:
        return False
    counts_by_dim = _group_counts_for_statement(statement_id, dims[:1], latest_votes)
    gmap = counts_by_dim.get(primary_dim, {})
    my_gc = gmap.get(my_group)
    if not my_gc or my_gc.n_ad < params.min_group_n:
        return False
    my_agree_prob = smoothed_rate(my_gc, params)
    prob_my_vote = my_agree_prob if ev.value == 1 else (1.0 - my_agree_prob)
    if prob_my_vote > params.surprise_threshold:
        return False
    # 別の立場でその票が多数派（>= 0.6）になっているか
    for other_grp, other_gc in gmap.items():
        if other_grp == my_group or other_gc.n_ad < params.min_group_n:
            continue
        other_agree = smoothed_rate(other_gc, params)
        other_prob = other_agree if ev.value == 1 else (1.0 - other_agree)
        if other_prob >= 0.60:
            return True
    return False


def build_story_cards(
    db: Session,
    topic: Topic,
    statement_id: int,
    current_user_id: int | None,
    latest_votes: dict[tuple[int, int], VoteEvent] | None = None,
    params: Params = DEFAULT_PARAMS,
) -> dict[str, list[dict[str, Any]]]:
    """2.8 体験談の順位づけ（立場を越えた理解 CU + 共感 R + 境界人ボーナス）を適用して返す。"""
    if latest_votes is None:
        latest_votes = get_latest_votes(db, topic.id)

    links = db.scalars(
        select(StoryStatementLink).where(StoryStatementLink.statement_id == statement_id)
    ).all()
    if not links:
        return {"supports": [], "opposes": [], "context": []}

    story_ids = [lnk.story_id for lnk in links]
    stance_by_story = {lnk.story_id: lnk.stance for lnk in links}
    stories = db.scalars(select(Story).where(Story.id.in_(story_ids))).all()
    reactions = db.scalars(select(StoryReaction).where(StoryReaction.story_id.in_(story_ids))).all()

    reactions_by_story: dict[int, list[StoryReaction]] = defaultdict(list)
    for r in reactions:
        reactions_by_story[r.story_id].append(r)

    dims = get_dimensions_for_topic(topic)
    primary_dim = dims[0][0] if dims else None
    primary_groups = [g for g in (dims[0][2] if dims else []) if g != "当てはまらない"]

    grouped: dict[str, list[ tuple[float, dict[str, Any]] ]] = {
        "supports": [],
        "opposes": [],
        "context": [],
    }

    for st in stories:
        snap = st.position_snapshot or {}
        author_pos = snap.get(primary_dim) if primary_dim else None
        boundary = is_boundary_voter(topic, statement_id, st.author_id, snap, latest_votes, params)
        r_list = reactions_by_story.get(st.id, [])
        n_resonate = sum(1 for r in r_list if r.kind == "resonate")
        n_understand = sum(1 for r in r_list if r.kind == "understand")
        my_reacs = [r.kind for r in r_list if current_user_id and r.user_id == current_user_id]

        # 2.8 CU（異なる立場からの「理解できた」の幾何平均）と R（同じ立場からの「共感」）
        other_groups = [g for g in primary_groups if g != author_pos]
        if other_groups and primary_dim:
            cu_terms = []
            for g in other_groups:
                u_gt = sum(
                    1
                    for r in r_list
                    if r.kind == "understand" and (r.position_snapshot or {}).get(primary_dim) == g
                )
                v_gt = max(u_gt, len([r for r in r_list if (r.position_snapshot or {}).get(primary_dim) == g]))
                cu_terms.append((u_gt + 1.0) / (v_gt + 2.0))
            cu = float(np.prod(cu_terms) ** (1.0 / len(cu_terms)))
        else:
            cu = (n_understand + 1.0) / (len(r_list) + 2.0)

        same_res = sum(
            1
            for r in r_list
            if r.kind == "resonate" and (not primary_dim or (r.position_snapshot or {}).get(primary_dim) == author_pos)
        )
        r_score = (same_res + 1.0) / (len(r_list) + 2.0)
        score = 0.5 * cu + 0.3 * r_score + (0.2 if boundary else 0.0)

        card = {
            "id": st.id,
            "kind": st.kind,
            "summary": st.summary or st.body[:75],
            "body": st.body,
            "stance": stance_by_story.get(st.id, "supports"),
            "author_position_label": author_pos,
            "is_boundary": boundary,
            "is_mine": bool(current_user_id and st.author_id == current_user_id),
            "reactions": {"resonate": n_resonate, "understand": n_understand},
            "my_reactions": my_reacs,
        }
        grouped.setdefault(card["stance"], []).append((score, card))

    return {
        k: [card for _, card in sorted(v, key=lambda x: (-x[0], -x[1]["id"]))]
        for k, v in grouped.items()
    }


def run_analysis(db: Session, topic_id: int, params: Params = DEFAULT_PARAMS) -> dict[str, Any]:
    """トピック全体の分析を実行し、スナップショットと成果物（必要な場合）を更新する。"""
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise ValueError("Topic not found")

    statements = db.scalars(
        select(Statement)
        .where(Statement.topic_id == topic_id, Statement.status == "active")
        .order_by(Statement.id.asc())
    ).all()
    statement_ids = [s.id for s in statements]
    latest_votes = get_latest_votes(db, topic_id)
    last_vote_id = max((ev.id for ev in latest_votes.values()), default=0)

    # 前回のスナップショットの中心座標を取得（ハンガリアン法でのID維持用）
    prev_snap = db.scalars(
        select(AnalysisSnapshot)
        .where(AnalysisSnapshot.topic_id == topic_id)
        .order_by(AnalysisSnapshot.id.desc())
    ).first()
    prev_centers = None
    if prev_snap and prev_snap.meta and "centers" in prev_snap.meta:
        prev_centers = np.array(prev_snap.meta["centers"], dtype=float)

    votes_int = {k: ev.value for k, ev in latest_votes.items()}
    omap = opinion_map(votes_int, statement_ids, params, prev_centers=prev_centers, seed=42)

    dims = get_dimensions_for_topic(topic)
    dim_keys = [d[0] for d in dims]
    dim_labels = {d[0]: d[1] for d in dims}
    primary_dim = dims[0][0] if dims else None

    rng = np.random.default_rng(42)

    # 原則ごとの統計と p 値の計算
    raw_stats: dict[int, dict[str, Any]] = {}
    pvals_for_bh: dict[int, float] = {}
    group_counts_all: dict[int, dict[str, dict[str, GroupCount]]] = {}

    for st in statements:
        sid = st.id
        counts_by_dim = _group_counts_for_statement(sid, dims, latest_votes)
        group_counts_all[sid] = counts_by_dim

        n_agree = sum(1 for (u, s), ev in latest_votes.items() if s == sid and ev.value == 1)
        n_disagree = sum(1 for (u, s), ev in latest_votes.items() if s == sid and ev.value == -1)
        n_pass = sum(1 for (u, s), ev in latest_votes.items() if s == sid and ev.value == 0)

        # 投票者の立場行リスト（PD 計算用）
        ad_rows: list[dict[str, str]] = []
        ad_y: list[int] = []
        for (_, s), ev in latest_votes.items():
            if s == sid and ev.value in (1, -1):
                ad_rows.append(ev.position_snapshot or {})
                ad_y.append(1 if ev.value == 1 else 0)

        pd_overall = position_dependence(ad_rows, ad_y, dim_keys, params, seed=42)
        pd_by_dim: dict[str, float] = {}
        for dk in dim_keys:
            val = position_dependence(ad_rows, ad_y, [dk], params, seed=42)
            if val is not None:
                pd_by_dim[dk] = round(val, 4)

        best_gap: float | None = None
        best_gap_dim: str | None = None
        best_pval: float | None = None
        for dk, _, _ in dims:
            gmap = {k: v for k, v in counts_by_dim.get(dk, {}).items() if k != "当てはまらない"}
            g_val = gap(gmap, params)
            p_val = independence_p(gmap, params, rng)
            if g_val is not None and (best_gap is None or g_val > best_gap):
                best_gap = g_val
                best_gap_dim = dk
                best_pval = p_val

        # 第一軸での GIC
        primary_groups = [
            v
            for k, v in counts_by_dim.get(primary_dim or "", {}).items()
            if k != "当てはまらない" and v.n_ad >= params.min_group_n
        ]
        gic_val = gic(primary_groups) if primary_groups else None

        if best_pval is not None:
            pvals_for_bh[sid] = best_pval

        raw_stats[sid] = {
            "n_seen": n_agree + n_disagree + n_pass,
            "n_agree": n_agree,
            "n_disagree": n_disagree,
            "n_pass": n_pass,
            "gic": round(gic_val, 4) if gic_val is not None else None,
            "pd": round(pd_overall, 4) if pd_overall is not None else None,
            "pd_by_dimension": pd_by_dim,
            "gap": round(best_gap, 4) if best_gap is not None else None,
            "gap_dimension": best_gap_dim,
            "p_value": round(best_pval, 6) if best_pval is not None else None,
            "primary_groups": primary_groups,
            "origin": st.origin,
            "body": st.body,
        }

    qvals = benjamini_hochberg(pvals_for_bh)

    # 2.9 セクション分類（機械的ルール）
    sections_map: dict[str, list[int]] = {
        "consensus": [],
        "divergence": [],
        "bridge": [],
        "value_split": [],
        "undecided": [],
    }
    for st in statements:
        sid = st.id
        info = raw_stats[sid]
        q_val = qvals.get(sid)
        info["q_value"] = round(q_val, 6) if q_val is not None else None
        n_ad = info["n_agree"] + info["n_disagree"]
        p_groups: list[GroupCount] = info["primary_groups"]
        rates = [smoothed_rate(g, params) for g in p_groups]
        overall_rate = info["n_agree"] / n_ad if n_ad > 0 else 0.0

        is_bridge_candidate = info["origin"] == "ai_bridge" or any(
            w in info["body"] for w in ("条件", "限り", "場合のみ")
        )

        if n_ad < params.min_total_n or len(rates) < 2:
            sec = "undecided"
        elif all(r >= params.consensus_rate for r in rates):
            sec = "consensus"
        elif is_bridge_candidate and all(r >= params.bridge_rate for r in rates):
            sec = "bridge"
        elif (
            q_val is not None
            and q_val < params.divergence_q
            and info["gap"] is not None
            and info["gap"] >= params.divergence_gap
        ):
            sec = "divergence"
        elif params.value_split_low <= overall_rate <= params.value_split_high:
            sec = "value_split"
        else:
            sec = "undecided"

        info["section"] = sec
        sections_map[sec].append(sid)

    # 2.5 トピック全体の立場依存度（NMI）とクラスター情報
    user_latest_snap: dict[int, dict[str, str]] = {}
    for (u, _), ev in latest_votes.items():
        if ev.position_snapshot:
            user_latest_snap[u] = ev.position_snapshot

    topic_dep: list[dict[str, Any]] = []
    if omap.available and len(omap.user_ids) >= params.min_group_n:
        for dk, dlabel, _ in dims:
            c_Arr = []
            p_Arr = []
            for uid, cl in zip(omap.user_ids, omap.labels):
                grp = user_latest_snap.get(uid, {}).get(dk)
                if grp and grp != "当てはまらない":
                    c_Arr.append(int(cl))
                    p_Arr.append(grp)
            if len(set(c_Arr)) >= 2 and len(set(p_Arr)) >= 2:
                nmi = float(normalized_mutual_info(c_Arr, p_Arr))
                topic_dep.append({"dimension": dk, "label": dlabel, "nmi": round(nmi, 4)})

    clusters_meta: list[dict[str, Any]] = []
    if omap.available:
        for cid in sorted(set(int(x) for x in omap.labels)):
            c_users = {u for u, l in zip(omap.user_ids, omap.labels) if int(l) == cid}
            pts = np.array([[omap.positions_by_user[u][0], omap.positions_by_user[u][1]] for u in c_users])
            cx, cy = (float(pts[:, 0].mean()), float(pts[:, 1].mean())) if len(pts) else (0.0, 0.0)
            stmt_rates = []
            for st in statements:
                ag = sum(1 for u in c_users if votes_int.get((u, st.id)) == 1)
                dis = sum(1 for u in c_users if votes_int.get((u, st.id)) == -1)
                if ag + dis >= 3:
                    stmt_rates.append(
                        {"id": st.id, "text": st.body, "agree_rate": round(ag / (ag + dis), 3)}
                    )
            stmt_rates.sort(key=lambda x: x["agree_rate"], reverse=True)
            clusters_meta.append(
                {
                    "id": cid,
                    "size": len(c_users),
                    "cx": round(cx, 4),
                    "cy": round(cy, 4),
                    "top_statements": stmt_rates[:3],
                }
            )

    snap_row = AnalysisSnapshot(
        topic_id=topic_id,
        last_vote_event_id=last_vote_id,
        params=params.to_dict(),
        meta={
            "available": omap.available,
            "reason": omap.reason,
            "centers": omap.centers.tolist() if len(omap.centers) else [],
            "clusters": clusters_meta,
            "topic_dependency": topic_dep,
            "dim_labels": dim_labels,
        },
    )
    db.add(snap_row)
    db.flush()

    for st in statements:
        sid = st.id
        info = raw_stats[sid]
        db.add(
            StatementStats(
                snapshot_id=snap_row.id,
                statement_id=sid,
                n_seen=info["n_seen"],
                n_agree=info["n_agree"],
                n_disagree=info["n_disagree"],
                n_pass=info["n_pass"],
                gic=info["gic"],
                pd=info["pd"],
                pd_by_dimension=info["pd_by_dimension"],
                gap=info["gap"],
                gap_dimension=info["gap_dimension"],
                p_value=info["p_value"],
                q_value=info["q_value"],
                section=info["section"],
            )
        )
        for dk, gmap in group_counts_all[sid].items():
            for gk, gc in gmap.items():
                if gc.n_seen > 0:
                    db.add(
                        GroupStats(
                            snapshot_id=snap_row.id,
                            statement_id=sid,
                            group_type="position",
                            dimension=dk,
                            group_key=gk,
                            n_seen=gc.n_seen,
                            n_agree=gc.n_agree,
                            n_disagree=gc.n_disagree,
                        )
                    )

    for uid, (x, y, cid) in omap.positions_by_user.items():
        db.add(
            UserProjection(
                snapshot_id=snap_row.id,
                user_id=uid,
                x=round(x, 4),
                y=round(y, 4),
                cluster_id=cid,
            )
        )

    # 成果物レポートの更新判定
    prev_report = db.scalars(
        select(ReportVersion)
        .where(ReportVersion.topic_id == topic_id)
        .order_by(ReportVersion.id.desc())
    ).first()

    prev_sections = prev_report.sections if prev_report else None
    report_version_str: str | None = prev_report.version if prev_report else None

    if prev_sections != sections_map:
        if prev_report is None:
            new_ver = "1.0"
        else:
            major, minor = prev_report.version.split(".")
            new_ver = f"{major}.{int(minor) + 1}"

        # セクション別の詳細データを組み立て
        sections_data: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for st in statements:
            sid = st.id
            info = raw_stats[sid]
            sec = info["section"]
            g_dim = info["gap_dimension"] or primary_dim or ""
            g_rates = []
            for gk, gc in group_counts_all[sid].get(g_dim, {}).items():
                if gk != "当てはまらない" and gc.n_ad >= params.min_group_n:
                    g_rates.append((gk, smoothed_rate(gc, params)))
            story_cards_map = build_story_cards(db, topic, sid, None, latest_votes, params)
            all_cards = (
                story_cards_map.get("supports", [])[:2]
                + story_cards_map.get("opposes", [])[:2]
                + story_cards_map.get("context", [])[:1]
            )
            sections_data[sec].append(
                {
                    "id": sid,
                    "body": st.body,
                    "gap": info["gap"],
                    "gap_dimension_label": dim_labels.get(g_dim, "立場"),
                    "group_rates": g_rates,
                    "stories": all_cards,
                }
            )

        # 参加者内訳（最小人数ルール適用）
        pos_counts: dict[str, dict[str, int]] = {}
        for dk, dlabel, _ in dims:
            cnt: dict[str, int] = defaultdict(int)
            for snap in user_latest_snap.values():
                val = snap.get(dk)
                if val:
                    cnt[val] += 1
            cleaned_cnt: dict[str, int] = {}
            small_sum = 0
            for k, v in cnt.items():
                if v >= params.min_group_n:
                    cleaned_cnt[k] = v
                else:
                    small_sum += v
            if small_sum > 0:
                cleaned_cnt["その他（少人数）"] = small_sum
            if cleaned_cnt:
                pos_counts[dlabel] = cleaned_cnt

        compiled = compile_report(
            topic_title=topic.title,
            topic_desc=topic.description,
            version=new_ver,
            n_participants=len(user_latest_snap),
            position_counts=pos_counts,
            params=params.to_dict(),
            sections_data=sections_data,
        )

        rep = ReportVersion(
            topic_id=topic_id,
            version=new_ver,
            snapshot_id=snap_row.id,
            body_md=compiled["body_md"],
            generator=compiled["generator"],
            sections=sections_map,
            diff={"prev_version": prev_report.version if prev_report else None},
        )
        db.add(rep)
        db.flush()

        for cit in compiled["citations"]:
            db.add(
                ReportCitation(
                    report_version_id=rep.id,
                    section_key=cit["section_key"],
                    ref_type=cit["ref_type"],
                    ref_id=cit["ref_id"],
                )
            )

        _record_contributions(db, rep, statements, compiled["citations"], latest_votes)
        report_version_str = new_ver

    db.commit()
    return {"snapshot_id": snap_row.id, "report_version": report_version_str}


def _record_contributions(
    db: Session,
    rep: ReportVersion,
    statements: list[Statement],
    citations: list[dict[str, Any]],
    latest_votes: dict[tuple[int, int], VoteEvent],
) -> None:
    """2.10 マクロ報酬（貢献の記録）を保存する。"""
    stmt_by_id = {s.id: s for s in statements}
    adopted_ids = set(
        rep.sections.get("consensus", [])
        + rep.sections.get("divergence", [])
        + rep.sections.get("bridge", [])
    )

    # 1. 原則の採用
    for sid in adopted_ids:
        st = stmt_by_id.get(sid)
        if st and st.author_id:
            db.add(
                Contribution(
                    user_id=st.author_id,
                    report_version_id=rep.id,
                    kind="statement_adopted",
                    ref_type="statement",
                    ref_id=sid,
                    weight=1.0,
                )
            )

    # 2. 体験談の引用
    cited_story_ids = {c["ref_id"] for c in citations if c["ref_type"] == "story"}
    if cited_story_ids:
        cited_stories = db.scalars(select(Story).where(Story.id.in_(cited_story_ids))).all()
        for st_obj in cited_stories:
            db.add(
                Contribution(
                    user_id=st_obj.author_id,
                    report_version_id=rep.id,
                    kind="story_cited",
                    ref_type="story",
                    ref_id=st_obj.id,
                    weight=1.0,
                )
            )

    # 3. 採用された原則への投票貢献
    for sid in adopted_ids:
        voters = [ev for (_, s), ev in latest_votes.items() if s == sid and ev.value in (1, -1)]
        if not voters:
            continue
        w = round(1.0 / len(voters), 4)
        for ev in voters:
            db.add(
                Contribution(
                    user_id=ev.user_id,
                    report_version_id=rep.id,
                    kind="vote",
                    ref_type="statement",
                    ref_id=sid,
                    weight=w,
                )
            )


def get_map_data(
    db: Session,
    topic: Topic,
    current_user_id: int | None,
    params: Params = DEFAULT_PARAMS,
) -> dict[str, Any]:
    snap = db.scalars(
        select(AnalysisSnapshot)
        .where(AnalysisSnapshot.topic_id == topic.id)
        .order_by(AnalysisSnapshot.id.desc())
    ).first()
    dims = get_dimensions_for_topic(topic)
    dim_list = [{"key": d[0], "label": d[1]} for d in dims]
    if snap is None or not snap.meta.get("available", False):
        return {
            "available": False,
            "reason": (snap.meta.get("reason") if snap else "まだ分析が実行されていません"),
            "snapshot_id": snap.id if snap else None,
            "computed_at": snap.computed_at.isoformat() if snap else None,
            "points": [],
            "clusters": [],
            "dimensions": dim_list,
            "topic_dependency": [],
        }

    projs = db.scalars(
        select(UserProjection).where(UserProjection.snapshot_id == snap.id)
    ).all()
    latest_votes = get_latest_votes(db, topic.id)
    user_snap: dict[int, dict[str, str]] = {}
    for (u, _), ev in latest_votes.items():
        if ev.position_snapshot:
            user_snap[u] = ev.position_snapshot

    # 最小人数ルール（10人未満の属性ラベルは「その他」にまとめる）
    label_counts: dict[str, dict[str, int]] = {d[0]: defaultdict(int) for d in dims}
    for p in projs:
        us = user_snap.get(p.user_id, {})
        for d_key, _, _ in dims:
            val = us.get(d_key)
            if val:
                label_counts[d_key][val] += 1

    points = []
    for p in projs:
        us = user_snap.get(p.user_id, {})
        groups: dict[str, str] = {}
        for d_key, _, _ in dims:
            val = us.get(d_key)
            if not val:
                groups[d_key] = "未選択"
            elif label_counts[d_key][val] < params.min_group_n:
                groups[d_key] = "その他"
            else:
                groups[d_key] = val
        points.append(
            {
                "x": p.x,
                "y": p.y,
                "cluster": p.cluster_id,
                "is_me": bool(current_user_id and p.user_id == current_user_id),
                "groups": groups,
            }
        )

    return {
        "available": True,
        "reason": None,
        "snapshot_id": snap.id,
        "computed_at": snap.computed_at.isoformat(),
        "points": points,
        "clusters": snap.meta.get("clusters", []),
        "dimensions": dim_list,
        "topic_dependency": snap.meta.get("topic_dependency", []),
    }


def get_diagnosis_data(
    db: Session,
    topic: Topic,
    current_user_id: int | None,
    params: Params = DEFAULT_PARAMS,
) -> dict[str, Any]:
    if not current_user_id:
        return {
            "ready": False,
            "needed": params.diag_min_items,
            "cluster": None,
            "typicality": None,
            "distinctive": [],
            "stories": {"same": None, "other": None},
        }

    snap = db.scalars(
        select(AnalysisSnapshot)
        .where(AnalysisSnapshot.topic_id == topic.id)
        .order_by(AnalysisSnapshot.id.desc())
    ).first()
    if snap is None:
        return {
            "ready": False,
            "needed": params.diag_min_items,
            "cluster": None,
            "typicality": None,
            "distinctive": [],
            "stories": {"same": None, "other": None},
        }

    latest_votes = get_latest_votes(db, topic.id)
    my_votes = {
        s: ev.value
        for (u, s), ev in latest_votes.items()
        if u == current_user_id and ev.value in (1, -1)
    }

    proj = db.scalars(
        select(UserProjection).where(
            UserProjection.snapshot_id == snap.id,
            UserProjection.user_id == current_user_id,
        )
    ).first()
    my_cluster = proj.cluster_id if proj else None

    dims = get_dimensions_for_topic(topic)
    primary_dim, primary_label = (dims[0][0], dims[0][1]) if dims else ("", "立場")
    my_snap = get_user_position_snapshot(db, current_user_id, topic.id)
    my_group = my_snap.get(primary_dim)

    st_stats = db.scalars(
        select(StatementStats).where(StatementStats.snapshot_id == snap.id)
    ).all()
    statements_by_id = {
        s.id: s
        for s in db.scalars(select(Statement).where(Statement.topic_id == topic.id)).all()
    }

    # 立場によって割れている原則 D（q < diag_q かつ gap >= diag_gap）
    div_sids = [
        st.statement_id
        for st in st_stats
        if (st.q_value is not None and st.q_value < params.diag_q)
        and (st.gap is not None and st.gap >= params.diag_gap)
    ]
    voted_div = [sid for sid in div_sids if sid in my_votes]
    required_items = min(params.diag_min_items, max(1, len(div_sids)))
    if len(voted_div) < required_items:
        return {
            "ready": False,
            "needed": max(1, required_items - len(voted_div)),
            "cluster": my_cluster,
            "typicality": None,
            "distinctive": [],
            "stories": {"same": None, "other": None},
        }

    matched = 0
    total = 0
    distinctive_candidates: list[tuple[float, dict[str, Any]]] = []

    if my_group and primary_dim:
        for sid in voted_div:
            counts_by_dim = _group_counts_for_statement(sid, dims[:1], latest_votes)
            gc = counts_by_dim.get(primary_dim, {}).get(my_group)
            if not gc or gc.n_ad < params.min_group_n:
                continue
            rate_agree = smoothed_rate(gc, params)
            maj_vote = 1 if rate_agree >= 0.5 else -1
            my_v = my_votes[sid]
            total += 1
            if my_v == maj_vote:
                matched += 1
            prob_my = rate_agree if my_v == 1 else (1.0 - rate_agree)
            if prob_my <= params.surprise_threshold and sid in statements_by_id:
                distinctive_candidates.append(
                    (
                        surprise_bits(prob_my),
                        {
                            "statement_id": sid,
                            "text": statements_by_id[sid].body,
                            "my_vote": my_v,
                            "group_label": my_group,
                            "group_vote_rate": round(prob_my, 3),
                        },
                    )
                )

    distinctive_candidates.sort(key=lambda x: x[0], reverse=True)
    typicality = (
        {
            "score": round(matched / total, 3),
            "matched": matched,
            "total": total,
            "dimension_label": primary_label,
            "group_label": my_group,
        }
        if (total > 0 and my_group)
        else None
    )

    # 同じクラスター／異なるクラスターの代表的な体験談を1件ずつ選ぶ
    same_story = None
    other_story = None
    all_Projs = {
        p.user_id: p.cluster_id
        for p in db.scalars(select(UserProjection).where(UserProjection.snapshot_id == snap.id)).all()
    }
    for sid in voted_div:
        cards_by_stance = build_story_cards(db, topic, sid, current_user_id, latest_votes, params)
        for c in cards_by_stance["supports"] + cards_by_stance["opposes"]:
            st_obj = db.get(Story, c["id"])
            if not st_obj:
                continue
            author_cl = all_Projs.get(st_obj.author_id)
            if my_cluster is not None and author_cl == my_cluster and same_story is None:
                same_story = c
            elif my_cluster is not None and author_cl is not None and author_cl != my_cluster and other_story is None:
                other_story = c
        if same_story and other_story:
            break

    return {
        "ready": True,
        "needed": 0,
        "cluster": my_cluster,
        "typicality": typicality,
        "distinctive": [x[1] for x in distinctive_candidates[:3]],
        "stories": {"same": same_story, "other": other_story},
    }
