"""Tests for the fee + slippage model."""

from __future__ import annotations

import pytest

from src.backtest.fees import ALPACA_PAPER, PESSIMISTIC, ZERO_COST, FeeModel


class TestFeeModel:
    def test_zero_cost_returns_zero(self) -> None:
        assert ZERO_COST.fill_cost(100, 50.0) == 0.0
        assert ZERO_COST.adjust_fill_price(50.0, "long") == 50.0
        assert ZERO_COST.adjust_fill_price(50.0, "short") == 50.0

    def test_alpaca_paper_slippage_only(self) -> None:
        # 100 shares × $50 × 1bp = $0.50 slippage
        assert ALPACA_PAPER.fill_cost(100, 50.0) == pytest.approx(0.50)

    def test_pessimistic_includes_commission(self) -> None:
        # 100 shares × $0.005 = $0.50 commission
        # 100 × $50 × 3bp = $1.50 slippage
        # total = $2.00
        assert PESSIMISTIC.fill_cost(100, 50.0) == pytest.approx(2.00)

    def test_long_slippage_pushes_price_up(self) -> None:
        adj = ALPACA_PAPER.adjust_fill_price(100.0, "long")
        assert adj > 100.0
        assert adj == pytest.approx(100.0 * (1 + 1e-4))

    def test_short_slippage_pushes_price_down(self) -> None:
        adj = ALPACA_PAPER.adjust_fill_price(100.0, "short")
        assert adj < 100.0

    def test_zero_shares_zero_cost(self) -> None:
        assert ALPACA_PAPER.fill_cost(0, 100.0) == 0.0

    def test_commission_min_floor(self) -> None:
        # 1 share × $0.005 = $0.005 commission, but min is $1
        fm = FeeModel(commission_per_share=0.005, commission_min=1.0, slippage_bps_per_side=0.0)
        assert fm.fill_cost(1, 50.0) == pytest.approx(1.0)
