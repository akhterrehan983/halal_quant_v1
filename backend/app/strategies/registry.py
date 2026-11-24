from __future__ import annotations

from app.strategies.base import BaseStrategy
from app.strategies.breakout.strategy import strategy as breakout_strategy
from app.strategies.high_momentum.strategy import strategy as high_momentum_strategy
from app.strategies.mean_reversion.strategy import strategy as mean_reversion_strategy
from app.strategies.momentum.strategy import strategy as momentum_strategy
from app.strategies.pullback.strategy import strategy as pullback_strategy
from app.strategies.trend_following.strategy import strategy as trend_following_strategy

_REGISTRY: dict[str, BaseStrategy] = {}
_ENABLED: dict[str, bool] = {}


def _bootstrap() -> None:
    if _REGISTRY:
        return
    for s in (
        momentum_strategy,
        breakout_strategy,
        pullback_strategy,
        mean_reversion_strategy,
        trend_following_strategy,
        high_momentum_strategy,
    ):
        _REGISTRY[s.strategy_id] = s
        _ENABLED[s.strategy_id] = True


def list_strategies() -> list[BaseStrategy]:
    _bootstrap()
    return list(_REGISTRY.values())


def get_strategy(strategy_id: str) -> BaseStrategy | None:
    _bootstrap()
    return _REGISTRY.get(strategy_id)


def is_enabled(strategy_id: str) -> bool:
    _bootstrap()
    return _ENABLED.get(strategy_id, False)


def set_enabled(strategy_id: str, enabled: bool) -> None:
    _bootstrap()
    if strategy_id not in _REGISTRY:
        raise KeyError(f"Unknown strategy: {strategy_id}")
    _ENABLED[strategy_id] = enabled


def enabled_strategies() -> list[BaseStrategy]:
    _bootstrap()
    return [s for sid, s in _REGISTRY.items() if _ENABLED.get(sid)]