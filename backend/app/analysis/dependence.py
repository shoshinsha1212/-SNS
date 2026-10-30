"""2.4.1 立場依存度（PD）：立場だけで賛否をどれだけ予測できるか。

PD = max(0, 1 - L_model / L_0)
- L_model: 立場のダミー変数を使った L2 正則化ロジスティック回帰の、交差検証での対数損失
- L_0    : 学習データ全体の賛成率だけで予測した場合の、交差検証での対数損失
"""

from __future__ import annotations

import numpy as np

from .params import Params


def _one_hot(rows: list[dict[str, str]], dims: list[str]) -> np.ndarray:
    cats: list[tuple[str, str]] = []
    seen = set()
    for r in rows:
        for d in dims:
            key = (d, r.get(d, "__none__"))
            if key not in seen:
                seen.add(key)
                cats.append(key)
    index = {c: i for i, c in enumerate(cats)}
    X = np.zeros((len(rows), len(cats) + 1), dtype=float)
    X[:, -1] = 1.0  # 切片項
    for i, r in enumerate(rows):
        for d in dims:
            X[i, index[(d, r.get(d, "__none__"))]] = 1.0
    return X


def _fit_logistic_l2(X: np.ndarray, y: np.ndarray, reg: float = 1.0, max_iter: int = 25) -> np.ndarray:
    """ニュートン・ラフソン法（IRLS）による L2 正則化ロジスティック回帰。"""
    n_features = X.shape[1]
    w = np.zeros(n_features, dtype=float)
    pen = np.eye(n_features, dtype=float) * reg
    pen[-1, -1] = 1e-6  # 切片には強い正則化をかけない
    for _ in range(max_iter):
        z = np.clip(X @ w, -30.0, 30.0)
        p = 1.0 / (1.0 + np.exp(-z))
        grad = X.T @ (p - y) + pen @ w
        W_diag = np.maximum(p * (1.0 - p), 1e-6)
        H = (X.T * W_diag) @ X + pen
        step = np.linalg.solve(H, grad)
        w -= step
        if float(np.max(np.abs(step))) < 1e-5:
            break
    return w


def _log_loss(y_true: np.ndarray, p_pred: np.ndarray) -> float:
    p = np.clip(p_pred, 1e-7, 1.0 - 1e-7)
    return float(-np.mean(y_true * np.log(p) + (1.0 - y_true) * np.log(1.0 - p)))


def _stratified_folds(y: np.ndarray, k: int, seed: int) -> list[tuple[np.ndarray, np.ndarray]]:
    rng = np.random.default_rng(seed)
    pos_idx = np.where(y == 1)[0].copy()
    neg_idx = np.where(y == 0)[0].copy()
    rng.shuffle(pos_idx)
    rng.shuffle(neg_idx)
    pos_splits = np.array_split(pos_idx, k)
    neg_splits = np.array_split(neg_idx, k)
    all_idx = np.arange(len(y))
    folds = []
    for i in range(k):
        test = np.concatenate([pos_splits[i], neg_splits[i]])
        train = np.setdiff1d(all_idx, test)
        folds.append((train, test))
    return folds


def position_dependence(
    rows: list[dict[str, str]], y: list[int], dims: list[str], p: Params, seed: int = 0
) -> float | None:
    """rows[i] は i 番目の票を入れた人の立場（次元→グループ）、y[i] は 1=賛成 / 0=反対。"""
    y_arr = np.asarray(y, dtype=float)
    if len(y_arr) == 0 or not dims:
        return None
    n_pos = int(y_arr.sum())
    n_neg = len(y_arr) - n_pos
    if min(n_pos, n_neg) < max(p.pd_min_per_class, p.pd_folds):
        return None
    X = _one_hot(rows, dims)
    loss_model = 0.0
    loss_base = 0.0
    for train, test in _stratified_folds(y_arr, p.pd_folds, seed):
        w = _fit_logistic_l2(X[train], y_arr[train], reg=1.0)
        z = np.clip(X[test] @ w, -30.0, 30.0)
        prob = 1.0 / (1.0 + np.exp(-z))
        base = np.full(len(test), float(y_arr[train].mean()))
        loss_model += _log_loss(y_arr[test], prob) * len(test)
        loss_base += _log_loss(y_arr[test], base) * len(test)
    if loss_base <= 0:
        return None
    return float(max(0.0, 1.0 - loss_model / loss_base))
