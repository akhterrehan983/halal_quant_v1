from app.signals.schemas import UnifiedSignal


def rank_signals(signals: list[UnifiedSignal]) -> list[UnifiedSignal]:
    return sorted(
        signals,
        key=lambda s: (s.overall_score, s.consensus_effective_buys, s.agreement_level),
        reverse=True,
    )