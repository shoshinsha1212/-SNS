"""分析で使う既定のパラメータ（成果物にも記録する）。"""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Params:
    # 2.1 マップに載せる最小投票数
    min_votes_for_map: int = 7
    # 2.4.2 立場ごとの賛成率の平滑化（ベータ分布の事前分布）
    rate_alpha: float = 2.0
    rate_beta: float = 2.0
    # 最小人数ルール（賛成+反対がこの人数未満のグループは計算・表示しない）
    min_group_n: int = 10
    # 2.4.3 分岐点の条件
    divergence_q: float = 0.05
    divergence_gap: float = 0.30
    # セクション判定に必要な賛成+反対の合計人数
    min_total_n: int = 50
    # 2.9 共通原則・条件付き合意案の閾値
    consensus_rate: float = 0.70
    bridge_rate: float = 0.55
    value_split_low: float = 0.35
    value_split_high: float = 0.65
    # 2.6 個人診断で使う「立場で割れている原則」の条件（分岐点より緩い）
    diag_q: float = 0.10
    diag_gap: float = 0.20
    diag_min_items: int = 5
    surprise_threshold: float = 0.25
    # 2.4.1 PD の交差検証
    pd_folds: int = 5
    pd_min_per_class: int = 5
    # 2.2 クラスター数の候補
    k_min: int = 2
    k_max: int = 5

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_PARAMS = Params()
