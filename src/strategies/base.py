"""Strategy ABC + Signal dataclass.

A Strategy is a *function from bars to signals*. It does not place orders,
it does not size positions, it does not know about the broker. That
separation lets us:

* unit-test signal logic against synthetic data trivially,
* swap out execution engines (research backtester now, Nautilus later) without
  rewriting the strategy,
* enforce risk checks on every signal in one place (the risk engine, not
  scattered through strategy code).

A Signal carries everything the risk engine needs to evaluate the trade
and the execution engine needs to place it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import polars as pl

Side = Literal["long", "short"]


@dataclass(frozen=True, slots=True)
class Signal:
    """One requested trade.

    A signal is a *request*. The risk engine decides whether it becomes an
    order. The strategy never bypasses the risk engine.
    """

    ts: datetime            # bar timestamp that produced the signal
    symbol: str
    side: Side
    entry: float            # intended entry price (informational; actual fill at next-bar open)
    stop: float             # protective stop price (mandatory)
    target: float           # take-profit price (mandatory)
    invalidation: str       # human-readable condition; checked by exit logic
    regime_tag: str         # quant_regime of the entry bar
    categorical_state: str  # categorical_state of the entry bar
    expected_duration_bars: int  # for the journal — flags drift later
    notes: str = ""         # free-form, surfaces in reports
    meta: dict = field(default_factory=dict)  # strategy-specific extras

    def __post_init__(self) -> None:
        if self.side == "long":
            if not (self.stop < self.entry < self.target):
                raise ValueError(
                    f"Long signal must satisfy stop < entry < target; "
                    f"got stop={self.stop} entry={self.entry} target={self.target}"
                )
        else:  # short
            if not (self.target < self.entry < self.stop):
                raise ValueError(
                    f"Short signal must satisfy target < entry < stop; "
                    f"got stop={self.stop} entry={self.entry} target={self.target}"
                )

    @property
    def risk_per_share(self) -> float:
        """Absolute distance from entry to stop. Used by position sizing."""
        return abs(self.entry - self.stop)

    @property
    def reward_per_share(self) -> float:
        return abs(self.target - self.entry)

    @property
    def reward_to_risk(self) -> float:
        return self.reward_per_share / self.risk_per_share if self.risk_per_share > 0 else 0.0


class Strategy(ABC):
    """Base class for all strategies.

    Subclasses must implement ``generate_signals(df) -> list[Signal]``. The
    input frame is assumed to already have indicator + regime columns; the
    backtester pre-computes them once and reuses across the run.

    Optional hooks for trailing stops and mid-trade invalidation are provided
    as no-op defaults — most strategies don't need them. Strategies that do
    (e.g. trend-following with trailing stops) override the methods below.
    """

    #: Human-readable strategy name. Used in reports.
    name: str = "unnamed_strategy"

    #: Regime tags (quant_regime values) the strategy is allowed to fire in.
    allowed_quant_regimes: frozenset[str] = frozenset()

    #: Categorical states the strategy is allowed to fire in.
    allowed_categorical_states: frozenset[str] = frozenset()

    @abstractmethod
    def generate_signals(self, df: pl.DataFrame) -> list[Signal]:
        """Produce signals for the given bars frame.

        Implementations must:
        * NOT use future data (only rows ``<= T`` to decide at row T).
        * Skip any row whose regime is not in ``allowed_quant_regimes`` /
          ``allowed_categorical_states``.
        * Return signals sorted ascending by ``ts``.
        """

    # ------------------------------------------------------------------
    # Optional mid-trade hooks (default: no-op)
    # ------------------------------------------------------------------
    def update_trailing_stop(
        self,
        bar: dict,
        open_position: dict,
    ) -> float | None:
        """Optional: propose a new trailing stop level for an open position.

        Called by the research engine on every bar while a position is open,
        *before* the stop/target/force-close exit checks. Return a new stop
        price or ``None`` if no change.

        Safety rails: the engine **silently ignores any proposal that would
        widen the stop** (i.e. a proposed long stop below the current stop,
        or a proposed short stop above the current stop). Per
        ``risk_policy.md`` Section 6: "Stops can only be tightened, never
        widened."

        Default implementation returns None (no trailing).
        """
        return None

    def check_invalidation(
        self,
        bar: dict,
        open_position: dict,
    ) -> bool:
        """Optional: signal that the position's *thesis* is broken.

        Called by the research engine on every bar while a position is open,
        *after* the trailing-stop update but *before* the stop/target/force-
        close checks. Return ``True`` to exit immediately at the bar's close
        with ``exit_reason="invalidation"``.

        Use this for conditions like "VWAP crossed against the position" or
        "regime flipped to chaotic mid-trade" — situations where the trade's
        hypothesis is dead even though the stop hasn't been touched.

        Default implementation returns False (never invalidate).
        """
        return False
