"""Tests for the Signal dataclass — the contract between strategy and engine."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.strategies.base import Signal


def _base_kwargs(**overrides):
    base = {
        "ts": datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc),
        "symbol": "SPY",
        "side": "long",
        "entry": 100.0,
        "stop": 99.0,
        "target": 102.0,
        "invalidation": "regime change",
        "regime_tag": "range_low",
        "categorical_state": "consolidating",
        "expected_duration_bars": 12,
    }
    base.update(overrides)
    return base


class TestSignal:
    def test_long_valid_construction(self) -> None:
        s = Signal(**_base_kwargs())
        assert s.side == "long"
        assert s.risk_per_share == pytest.approx(1.0)
        assert s.reward_per_share == pytest.approx(2.0)
        assert s.reward_to_risk == pytest.approx(2.0)

    def test_short_valid_construction(self) -> None:
        s = Signal(**_base_kwargs(side="short", entry=100.0, stop=101.0, target=98.0))
        assert s.side == "short"
        assert s.risk_per_share == pytest.approx(1.0)
        assert s.reward_to_risk == pytest.approx(2.0)

    def test_long_rejects_inverted_stop(self) -> None:
        with pytest.raises(ValueError):
            Signal(**_base_kwargs(stop=101.0))  # stop above entry

    def test_long_rejects_inverted_target(self) -> None:
        with pytest.raises(ValueError):
            Signal(**_base_kwargs(target=99.5))  # target below entry

    def test_short_rejects_inverted(self) -> None:
        with pytest.raises(ValueError):
            Signal(**_base_kwargs(side="short", entry=100.0, stop=99.0, target=102.0))

    def test_frozen(self) -> None:
        s = Signal(**_base_kwargs())
        with pytest.raises(Exception):  # FrozenInstanceError
            s.entry = 999.0  # type: ignore[misc]
