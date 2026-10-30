"""2.3 合意度、2.4.2 立場間ギャップ、2.4.3 検定と多重比較の補正。"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.stats import chi2_contingency

from .params import Params


@dataclass
class GroupCount:
    """あるグループにおける、ある原則の票数。"""

    n_agree: int = 0
    n_disagree: int = 0
    n_pass: int = 0

    @property
    def n_ad(self) -> int:
        return self.n_agree + self.n_disagree

    @property
    def n_seen(self) -> int:
        return self.n_agree + self.n_disagree + self.n_pass


def smoothed_rate(c: GroupCount, p: Params) -> float:
    """ベータ分布で平滑化した賛成率（パスは除く）。"""
    return (c.n_agree + p.rate_alpha) / (c.n_ad + p.rate_alpha + p.rate_beta)


def laplace_agree(c: GroupCount) -> float:
    """Polis の合意度で使う賛成確率。分母は「見た人数」（パスを含む）。"""
    return (c.n_agree + 1) / (c.n_seen + 2)


def gic(groups: list[GroupCount]) -> float | None:
    """グループを考慮した合意度：全グループの賛成確率の積。"""
    if not groups:
        return None
    return float(np.prod([laplace_agree(g) for g in groups]))


def gap(groups: dict[str, GroupCount], p: Params) -> float | None:
    """最小人数を満たすグループ間の、平滑化賛成率の最大差。"""
    rates = [smoothed_rate(c, p) for c in groups.values() if c.n_ad >= p.min_group_n]
    if len(rates) < 2:
        return None
    return float(max(rates) - min(rates))


def independence_p(groups: dict[str, GroupCount], p: Params, rng: np.random.Generator) -> float | None:
    """「賛成/反対」×「立場」の独立性の検定の p 値。

    期待度数 5 未満のマスがあるときはラベルを入れ替える並べ替え検定に切り替える。
    """
    valid = [c for c in groups.values() if c.n_ad >= p.min_group_n]
    if len(valid) < 2:
        return None
    table = np.array([[c.n_agree, c.n_disagree] for c in valid], dtype=float)
    if table[:, 0].sum() == 0 or table[:, 1].sum() == 0:
        return 1.0
    stat, pval, _, expected = chi2_contingency(table, correction=False)
    if (expected >= 5).all():
        return float(pval)
    return _permutation_p(table, stat, rng)


def _permutation_p(table: np.ndarray, observed: float, rng: np.random.Generator, n_perm: int = 1000) -> float:
    sizes = table.sum(axis=1).astype(int)
    n_agree = int(table[:, 0].sum())
    total = int(sizes.sum())
    labels = np.repeat(np.arange(len(sizes)), sizes)
    votes = np.zeros(total, dtype=int)
    votes[:n_agree] = 1
    expected_agree = sizes * n_agree / total
    expected_dis = sizes - expected_agree
    hits = 0
    for _ in range(n_perm):
        rng.shuffle(votes)
        agree = np.bincount(labels, weights=votes, minlength=len(sizes))
        dis = sizes - agree
        with np.errstate(divide="ignore", invalid="ignore"):
            stat = np.nansum((agree - expected_agree) ** 2 / expected_agree) + np.nansum(
                (dis - expected_dis) ** 2 / expected_dis
            )
        if stat >= observed - 1e-12:
            hits += 1
    return (hits + 1) / (n_perm + 1)


def benjamini_hochberg(pvals: dict[int, float]) -> dict[int, float]:
    """Benjamini-Hochberg 法による q 値。"""
    if not pvals:
        return {}
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    q = [0.0] * m
    running = 1.0
    for i in range(m - 1, -1, -1):
        rank = i + 1
        running = min(running, items[i][1] * m / rank)
        q[i] = min(running, 1.0)
    return {items[i][0]: q[i] for i in range(m)}


def surprise_bits(prob: float) -> float:
    return -math.log2(max(prob, 1e-9))


def normalized_mutual_info(labels_a: list[Any], labels_b: list[Any]) -> float:
    """正規化相互情報量（NMI）の純粋な NumPy 実装。"""
    n = len(labels_a)
    if n == 0 or len(labels_b) != n:
        return 0.0
    ua = sorted(set(labels_a), key=str)
    ub = sorted(set(labels_b), key=str)
    if len(ua) < 2 or len(ub) < 2:
        return 0.0
    ia = {v: i for i, v in enumerate(ua)}
    ib = {v: i for i, v in enumerate(ub)}
    joint = np.zeros((len(ua), len(ub)), dtype=float)
    for a, b in zip(labels_a, labels_b):
        joint[ia[a], ib[b]] += 1.0
    joint /= n
    pa = joint.sum(axis=1, keepdims=True)
    pb = joint.sum(axis=0, keepdims=True)
    ha = -float(np.sum(pa[pa > 0] * np.log(pa[pa > 0])))
    hb = -float(np.sum(pb[pb > 0] * np.log(pb[pb > 0])))
    if ha + hb <= 1e-12:
        return 0.0
    denom = pa @ pb
    mask = joint > 0
    mi = float(np.sum(joint[mask] * np.log(joint[mask] / denom[mask])))
    return float(np.clip(2.0 * mi / (ha + hb), 0.0, 1.0))

