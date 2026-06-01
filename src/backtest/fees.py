"""Fee + slippage models.

Defaults match Alpaca paper trading (commission-free) plus a 1bp/side
slippage assumption — realistic for SPY/QQQ in liquid hours, conservative
otherwise. Override for stress-testing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FeeModel:
    """Per-fill commission + per-side slippage assumption.

    Cost of a single fill is::

        cost = max(commission_per_share * abs(shares),
                   commission_min,
                   commission_per_trade)
              + abs(shares) * fill_price * slippage_bps_per_side / 10_000

    Defaults: Alpaca-style commission-free + 1 bp slippage per side.
    """

    commission_per_share: float = 0.0
    commission_per_trade: float = 0.0
    commission_min: float = 0.0
    slippage_bps_per_side: float = 1.0  # 1 bp = 0.01%

    def fill_cost(self, shares: float, fill_price: float) -> float:
        """Total dollar cost of one fill (positive number to subtract)."""
        if shares == 0:
            return 0.0
        notional = abs(shares) * fill_price
        commission = max(
            abs(shares) * self.commission_per_share,
            self.commission_min,
            self.commission_per_trade,
        )
        slippage = notional * self.slippage_bps_per_side / 10_000.0
        return commission + slippage

    def adjust_fill_price(self, intended_price: float, side: str) -> float:
        """Apply slippage to the intended fill price.

        Long fills tick up by slippage; short fills tick down. Matches the
        cost charged in :meth:`fill_cost`, but expressed as a worse price so
        downstream P&L math uses the realistic execution price.
        """
        adj = intended_price * self.slippage_bps_per_side / 10_000.0
        if side == "long":
            return intended_price + adj
        return intended_price - adj


# Convenient pre-rolled models — pick one or build your own.
ALPACA_PAPER = FeeModel(slippage_bps_per_side=1.0)
"""Alpaca paper trading defaults: free commission, 1 bp slippage."""

PESSIMISTIC = FeeModel(slippage_bps_per_side=3.0, commission_per_share=0.005)
"""Stress test: 3 bps slippage + a half-cent per share commission."""

ZERO_COST = FeeModel(slippage_bps_per_side=0.0)
"""For correctness tests only — never use in a real backtest."""
