"""2.2 意見マップと意見クラスター（Polis 方式：PCA + k-means）。"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linear_sum_assignment

from .params import Params


def _pca_2d(X: np.ndarray) -> np.ndarray:
    """特異値分解（SVD）による2次元主成分分析。"""
    u, s, _ = np.linalg.svd(X, full_matrices=False)
    coords = u[:, :2] * s[:2]
    if coords.shape[1] < 2:
        coords = np.hstack([coords, np.zeros((coords.shape[0], 2 - coords.shape[1]))])
    # 符号の任意性を固定（最大の絶対値要素を正にする）
    for j in range(coords.shape[1]):
        idx = int(np.argmax(np.abs(coords[:, j])))
        if coords[idx, j] < 0:
            coords[:, j] *= -1
    return coords


def _kmeans_2d(
    coords: np.ndarray, k: int, seed: int = 0, n_init: int = 8, max_iter: int = 50
) -> tuple[np.ndarray, np.ndarray]:
    """2次元座標に対する k-means++ クラスタリング（純粋な NumPy 実装）。"""
    rng = np.random.default_rng(seed)
    n = len(coords)
    best_inertia = float("inf")
    best_labels = np.zeros(n, dtype=int)
    best_centers = coords[:k].copy()

    for _ in range(n_init):
        centers = np.empty((k, coords.shape[1]), dtype=float)
        centers[0] = coords[int(rng.integers(0, n))]
        for c_idx in range(1, k):
            dist_sq = np.min(
                np.sum((coords[:, None, :] - centers[None, :c_idx, :]) ** 2, axis=2),
                axis=1,
            )
            total = float(dist_sq.sum())
            if total <= 1e-12:
                centers[c_idx] = coords[int(rng.integers(0, n))]
            else:
                probs = dist_sq / total
                centers[c_idx] = coords[int(rng.choice(n, p=probs))]

        labels = np.zeros(n, dtype=int)
        for _ in range(max_iter):
            dists = np.sum((coords[:, None, :] - centers[None, :, :]) ** 2, axis=2)
            new_labels = np.argmin(dists, axis=1)
            if np.array_equal(new_labels, labels):
                break
            labels = new_labels
            for j in range(k):
                mask = labels == j
                if mask.any():
                    centers[j] = coords[mask].mean(axis=0)

        inertia = float(np.sum((coords - centers[labels]) ** 2))
        if inertia < best_inertia:
            best_inertia = inertia
            best_labels = labels.copy()
            best_centers = centers.copy()

    return best_labels, best_centers


def _silhouette(coords: np.ndarray, labels: np.ndarray) -> float:
    """シルエット係数（純粋な NumPy 実装）。"""
    unique = np.unique(labels)
    if len(unique) < 2:
        return -1.0
    diff = coords[:, None, :] - coords[None, :, :]
    dist = np.sqrt(np.sum(diff * diff, axis=2))
    n = len(coords)
    scores = np.zeros(n, dtype=float)
    for i in range(n):
        own = labels == labels[i]
        own[i] = False
        a = float(dist[i, own].mean()) if own.any() else 0.0
        b = min(
            float(dist[i, labels == c].mean())
            for c in unique
            if c != labels[i] and (labels == c).any()
        )
        denom = max(a, b)
        scores[i] = (b - a) / denom if denom > 1e-12 else 0.0
    return float(scores.mean())


@dataclass
class OpinionMap:
    user_ids: list[int]
    coords: np.ndarray  # (n, 2)
    labels: np.ndarray  # (n,)
    centers: np.ndarray  # (k, 2)
    available: bool = True
    reason: str | None = None
    positions_by_user: dict[int, tuple[float, float, int]] = field(default_factory=dict)


def build_matrix(
    votes: dict[tuple[int, int], int], statement_ids: list[int]
) -> tuple[list[int], np.ndarray]:
    """(user, statement) -> 票 から、欠損を NaN とした投票行列を作る。"""
    users = sorted({u for (u, _) in votes})
    u_index = {u: i for i, u in enumerate(users)}
    s_index = {s: j for j, s in enumerate(statement_ids)}
    M = np.full((len(users), len(statement_ids)), np.nan)
    for (u, s), v in votes.items():
        if s in s_index:
            M[u_index[u], s_index[s]] = v
    return users, M


def opinion_map(
    votes: dict[tuple[int, int], int],
    statement_ids: list[int],
    p: Params,
    prev_centers: np.ndarray | None = None,
    seed: int = 0,
) -> OpinionMap:
    users, M = build_matrix(votes, statement_ids)
    empty = OpinionMap([], np.zeros((0, 2)), np.zeros(0, dtype=int), np.zeros((0, 2)))
    if len(statement_ids) < 2:
        empty.available, empty.reason = False, "原則が2件以上必要です"
        return empty
    n_votes = (~np.isnan(M)).sum(axis=1)
    keep = n_votes >= p.min_votes_for_map
    if keep.sum() < 2 * p.k_min + 2:
        empty.available = False
        empty.reason = f"{p.min_votes_for_map}票以上投票した人が{2 * p.k_min + 2}人以上になるとマップが表示されます"
        return empty

    X = M[keep]
    kept_users = [u for u, k in zip(users, keep) if k]
    col_mean = np.nanmean(np.where(np.isnan(X).all(axis=0), 0, X), axis=0)
    col_mean = np.nan_to_num(col_mean)
    filled = np.where(np.isnan(X), col_mean, X)
    filled = filled - filled.mean(axis=0)

    coords = _pca_2d(filled)
    scale = np.sqrt(len(statement_ids) / n_votes[keep])
    coords = coords * scale[:, None]

    best: tuple[float, np.ndarray, np.ndarray] | None = None
    for k in range(p.k_min, p.k_max + 1):
        if k >= len(kept_users):
            break
        lbls, ctrs = _kmeans_2d(coords, k=k, seed=seed)
        if len(set(int(x) for x in lbls)) < 2:
            continue
        score = _silhouette(coords, lbls)
        if best is None or score > best[0]:
            best = (score, lbls, ctrs)
    if best is None:
        empty.available, empty.reason = False, "意見のグループを作れませんでした"
        return empty
    labels = best[1].copy()
    centers = best[2].copy()

    # 前回の中心と番号をそろえる（ハンガリアン法）
    if prev_centers is not None and len(prev_centers) > 0:
        cost = np.linalg.norm(centers[:, None, :] - prev_centers[None, :, :], axis=2)
        rows, cols = linear_sum_assignment(cost)
        mapping = {}
        used = set()
        for r, c in zip(rows, cols):
            mapping[r] = c
            used.add(c)
        next_id = max(len(prev_centers), len(centers))
        for r in range(len(centers)):
            if r not in mapping:
                while next_id in used:
                    next_id += 1
                mapping[r] = next_id
                used.add(next_id)
        labels = np.array([mapping[l] for l in labels])
        new_centers = np.zeros((max(mapping.values()) + 1, 2))
        for r, c in mapping.items():
            new_centers[c] = centers[r]
        centers = new_centers

    result = OpinionMap(kept_users, coords, labels, centers)
    result.positions_by_user = {
        u: (float(coords[i, 0]), float(coords[i, 1]), int(labels[i])) for i, u in enumerate(kept_users)
    }
    return result
