"""End-to-end tests for the research backtester.

These hand-craft tiny synthetic series with deterministic outcomes so we
can verify the engine: stop logic, target logic, fees, sizing, and equity
curve mechanics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from src.backtest.fees import ZERO_COST, FeeModel
from src.backtest.metrics import all_metrics, regime_slice, trade_stats
from src.backtest.research_engine import run_backtest
from src.strategies.base import Signal, Strategy


# ---- A test-only strategy that emits a single hand-crafted signal -----


class FixedSignalStrategy(Strategy):
    """Emits one signal at a chosen bar — for engine unit tests."""

    name = "fixed_signal"
    allowed_quant_regimes = frozenset()  # not enforced by engine
    allowed_categorical_states = frozenset()

    def __init__(self, signal: Signal) -> None:
        self._signal = signal

    def generate_signals(self, df: pl.DataFrame) -> list[Signal]:
        return [self._signal]


# ---- Helpers ----------------------------------------------------------


def _bars(closes: list[float], *, start_hour: int = 14) -> pl.DataFrame:
    """Build a minimal OHLCV frame.

    open=prev_close, close=close, high=max(open,close)+0.05, low=min(open,close)-0.05.
    All bars 5 minutes apart starting 2024-01-02 at 09:30 ET (14:30 UTC).
    """
    start = datetime(2024, 1, 2, start_hour, 30, tzinfo=timezone.utc)
    ts = [start + timedelta(minutes=5 * i) for i in range(len(closes))]
    opens = [closes[0]] + closes[:-1]
    highs = [max(o, c) + 0.05 for o, c in zip(opens, closes)]
    lows = [min(o, c) - 0.05 for o, c in zip(opens, closes)]
    return pl.DataFrame(
        {
            "ts": ts,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [10_000.0] * len(closes),
            "symbol": ["TEST"] * len(closes),
        }
    )


# ---- Tests ------------------------------------------------------------


class TestResearchEngineBasics:
    def test_no_signals_no_trades(self) -> None:
        class NoSignal(Strategy):
            name = "ns"
            allowed_quant_regimes = frozenset()
            allowed_categorical_states = frozenset()

            def generate_signals(self, df):
                return []

        bars = _bars([100.0] * 50)
        res = run_backtest(bars, NoSignal())
        assert res.n_trades == 0
        assert res.ending_equity == res.starting_equity
        assert res.equity_curve.height == 50

    def test_long_hits_target(self) -> None:
        # Bars: signal at bar 0 (close=100), price climbs to 105 at bar 5.
        closes = [100.0, 100.5, 101.0, 102.0, 103.0, 105.0] + [104.0] * 10
        bars = _bars(closes)
        sig = Signal(
            ts=bars["ts"][0],
            symbol="TEST",
            side="long",
            entry=100.0,
            stop=99.0,
            target=104.0,
            invalidation="x",
            regime_tag="range_low",
            categorical_state="consolidating",
            expected_duration_bars=10,
        )
        res = run_backtest(
            bars, FixedSignalStrategy(sig),
            starting_equity=100_000.0,
            risk_per_trade=0.01,
            fee_model=ZERO_COST,
        )
        assert res.n_trades == 1
        t = res.trades[0]
        assert t.exit_reason == "target"
        assert t.side == "long"
        # Realized stop distance is 100.5 (next-bar open) - 99 = 1.5
        # Shares = floor(100000 * 0.01 / 1.5) = 666
        assert t.shares == 666
        # P&L = (target - entry_fill) * shares = (104 - 100.5) * 666 = 2331
        assert t.pnl == pytest.approx((104.0 - 100.5) * 666, rel=1e-3)

    def test_long_hits_stop(self) -> None:
        # Bars drop sharply after entry — stop must fire.
        closes = [100.0, 100.5, 99.0, 98.0, 97.0] + [97.5] * 10
        bars = _bars(closes)
        sig = Signal(
            ts=bars["ts"][0],
            symbol="TEST",
            side="long",
            entry=100.0,
            stop=99.5,
            target=103.0,
            invalidation="x",
            regime_tag="range_low",
            categorical_state="consolidating",
            expected_duration_bars=10,
        )
        res = run_backtest(
            bars, FixedSignalStrategy(sig),
            risk_per_trade=0.01,
            fee_model=ZERO_COST,
        )
        assert res.n_trades == 1
        assert res.trades[0].exit_reason == "stop"
        assert res.trades[0].pnl < 0

    def test_short_hits_target(self) -> None:
        # Price falls from 100 to 95 — short target hit.
        closes = [100.0, 99.5, 99.0, 97.0, 95.0] + [95.5] * 10
        bars = _bars(closes)
        sig = Signal(
            ts=bars["ts"][0],
            symbol="TEST",
            side="short",
            entry=100.0,
            stop=101.0,
            target=96.0,
            invalidation="x",
            regime_tag="range_low",
            categorical_state="consolidating",
            expected_duration_bars=10,
        )
        res = run_backtest(
            bars, FixedSignalStrategy(sig),
            risk_per_trade=0.01,
            fee_model=ZERO_COST,
        )
        assert res.n_trades == 1
        assert res.trades[0].exit_reason == "target"
        assert res.trades[0].pnl > 0

    def test_force_close_at_session_end(self) -> None:
        # Build bars that span past 15:30 ET (= 20:30 UTC). Start 19:00 UTC.
        # 5-min bars: 19:00, 19:05, ... — by bar 19 we'll be at 20:35 UTC = 15:35 ET, past the cutoff.
        closes = [100.0] * 30
        bars = _bars(closes, start_hour=19)
        sig = Signal(
            ts=bars["ts"][0],
            symbol="TEST",
            side="long",
            entry=100.0,
            stop=99.0,
            target=110.0,
            invalidation="x",
            regime_tag="range_low",
            categorical_state="consolidating",
            expected_duration_bars=100,
        )
        res = run_backtest(bars, FixedSignalStrategy(sig), fee_model=ZERO_COST)
        assert res.n_trades == 1
        assert res.trades[0].exit_reason == "force_close"

    # ------------------------------------------------------------------
    # Guardrail tests (added 2026-05-24 after first real backtest produced
    # a 60x-leverage trade and 3-of-4 same-bar exits).
    # ------------------------------------------------------------------

    def test_max_notional_default_blocks_leverage_blowup(self) -> None:
        """Tight stop + standard risk_per_trade would size to >1x equity.

        Replicates the bug from the first SPY backtest: tiny stop distance
        caused shares = 250 / 0.10 = 2500 shares at $100 → $250k notional
        on $100k equity. With max_notional_pct=1.0 (default), this signal
        must be rejected and the counter must increment.
        """
        # 30 flat bars so nothing dramatic happens after the (rejected) entry.
        closes = [100.0] * 30
        bars = _bars(closes)
        # Stop is $0.10 away (= 10 bps of price → passes min_stop guard),
        # but at default risk 0.0025 of $100k = $250 risk, shares would be
        # 250/0.10 = 2500, and 2500 * $100 = $250k notional > $100k equity.
        sig = Signal(
            ts=bars["ts"][0],
            symbol="TEST",
            side="long",
            entry=100.0,
            stop=99.90,
            target=101.0,
            invalidation="x",
            regime_tag="range_low",
            categorical_state="consolidating",
            expected_duration_bars=5,
        )
        res = run_backtest(
            bars, FixedSignalStrategy(sig),
            starting_equity=100_000.0,
            risk_per_trade=0.0025,
            fee_model=ZERO_COST,
        )
        assert res.n_trades == 0, "Trade should have been skipped by notional cap"
        assert res.signals_skipped_by_max_notional == 1
        assert res.signals_skipped_by_min_stop == 0
        assert res.signals_skipped_by_sizing == 0
        assert res.ending_equity == res.starting_equity  # nothing happened

    def test_max_notional_can_be_raised_to_allow_leverage(self) -> None:
        """When the user explicitly asks for leverage, the engine obeys."""
        closes = [100.0, 100.0, 100.5, 101.0, 101.5] + [101.0] * 10
        bars = _bars(closes)
        sig = Signal(
            ts=bars["ts"][0],
            symbol="TEST",
            side="long",
            entry=100.0,
            stop=99.90,
            target=101.0,
            invalidation="x",
            regime_tag="range_low",
            categorical_state="consolidating",
            expected_duration_bars=5,
        )
        res = run_backtest(
            bars, FixedSignalStrategy(sig),
            starting_equity=100_000.0,
            risk_per_trade=0.0025,
            max_notional_pct=10.0,   # explicit 10x leverage cap
            fee_model=ZERO_COST,
        )
        assert res.n_trades == 1
        assert res.signals_skipped_by_max_notional == 0
        # Shares = floor(100000 * 0.0025 / 0.10) = 2500
        assert res.trades[0].shares == 2500

    def test_min_stop_default_blocks_microscopic_stop(self) -> None:
        """Stop tighter than 5 bps of price → skipped, not silently fired."""
        closes = [100.0] * 30
        bars = _bars(closes)
        # Stop is $0.03 away = 3 bps of $100 → below default 5 bps min_stop.
        sig = Signal(
            ts=bars["ts"][0],
            symbol="TEST",
            side="long",
            entry=100.0,
            stop=99.97,
            target=100.5,
            invalidation="x",
            regime_tag="range_low",
            categorical_state="consolidating",
            expected_duration_bars=5,
        )
        res = run_backtest(
            bars, FixedSignalStrategy(sig),
            starting_equity=100_000.0,
            risk_per_trade=0.0025,
            fee_model=ZERO_COST,
        )
        assert res.n_trades == 0
        assert res.signals_skipped_by_min_stop == 1
        assert res.signals_skipped_by_max_notional == 0
        assert res.signals_skipped_by_sizing == 0

    def test_min_stop_can_be_disabled(self) -> None:
        """Setting min_stop_pct=0 lets a microscopic stop through.

        (Combined with a generous notional cap so we can isolate the
        min-stop behaviour from the notional behaviour.)
        """
        # Make sure target is far enough above entry to not collide with
        # the upward drift, so we can see what the engine actually does.
        closes = [100.0, 100.0, 100.01, 100.02, 100.5] + [100.5] * 10
        bars = _bars(closes)
        sig = Signal(
            ts=bars["ts"][0],
            symbol="TEST",
            side="long",
            entry=100.0,
            stop=99.97,
            target=100.5,
            invalidation="x",
            regime_tag="range_low",
            categorical_state="consolidating",
            expected_duration_bars=10,
        )
        res = run_backtest(
            bars, FixedSignalStrategy(sig),
            starting_equity=100_000.0,
            risk_per_trade=0.0025,
            min_stop_pct=0.0,         # guard explicitly disabled
            max_notional_pct=100.0,   # generous so we isolate min_stop behavior
            fee_model=ZERO_COST,
        )
        # Engine accepted the signal (either it produced a trade or it
        # exited immediately, but min_stop did NOT block it).
        assert res.signals_skipped_by_min_stop == 0

    def test_invalid_max_notional_pct_raises(self) -> None:
        bars = _bars([100.0] * 10)

        class _NoSig(Strategy):
            name = "ns"
            allowed_quant_regimes = frozenset()
            allowed_categorical_states = frozenset()

            def generate_signals(self, df):
                return []

        with pytest.raises(ValueError, match="max_notional_pct"):
            run_backtest(bars, _NoSig(), max_notional_pct=0.0)

    def test_invalid_min_stop_pct_raises(self) -> None:
        bars = _bars([100.0] * 10)

        class _NoSig(Strategy):
            name = "ns"
            allowed_quant_regimes = frozenset()
            allowed_categorical_states = frozenset()

            def generate_signals(self, df):
                return []

        with pytest.raises(ValueError, match="min_stop_pct"):
            run_backtest(bars, _NoSig(), min_stop_pct=-0.01)

    def test_pessimistic_stop_vs_target_tie(self) -> None:
        # Bar 2 has high=105 (target) AND low=99 (stop). The engine MUST
        # report this as a stop hit (pessimistic assumption).
        closes = [100.0, 100.0, 102.0]
        bars = _bars(closes)
        # Manually widen bar 2 to touch both.
        bars = bars.with_columns(
            pl.when(pl.col("ts") == bars["ts"][2]).then(105.0).otherwise(pl.col("high")).alias("high"),
            pl.when(pl.col("ts") == bars["ts"][2]).then(99.0).otherwise(pl.col("low")).alias("low"),
        )
        sig = Signal(
            ts=bars["ts"][0],
            symbol="TEST",
            side="long",
            entry=100.0,
            stop=99.5,
            target=104.0,
            invalidation="x",
            regime_tag="range_low",
            categorical_state="consolidating",
            expected_duration_bars=5,
        )
        res = run_backtest(bars, FixedSignalStrategy(sig), fee_model=ZERO_COST)
        assert res.n_trades == 1
        assert res.trades[0].exit_reason == "stop"  # pessimistic


class TestMetrics:
    def _build_result_with_known_pnls(self, pnls: list[float]):
        # Build a synthetic BacktestResult-like object via run_backtest with
        # one trade per pnl. Easier: directly construct Trade objects.
        from src.backtest.research_engine import BacktestResult, Trade

        trades = [
            Trade(
                symbol="X",
                side="long",
                entry_ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
                exit_ts=datetime(2024, 1, 1, 1, tzinfo=timezone.utc),
                entry_price=100.0,
                exit_price=100.0 + p / 100,
                shares=100,
                pnl=p,
                pnl_pct=p / 100,
                bars_held=10,
                exit_reason="target" if p > 0 else "stop",
                regime_tag="range_low" if i % 2 == 0 else "range_medium",
                categorical_state="consolidating",
                fees_paid=0.0,
                risk_per_share=1.0,
            )
            for i, p in enumerate(pnls)
        ]
        return BacktestResult(
            strategy_name="x",
            symbol="X",
            starting_equity=100_000.0,
            ending_equity=100_000.0 + sum(pnls),
            trades=trades,
            equity_curve=pl.DataFrame({"ts": [], "equity": [], "open_position": []}),
            signals_generated=len(trades),
        )

    def test_trade_stats_basic(self) -> None:
        res = self._build_result_with_known_pnls([100, -50, 200, -75, 300])
        ts = trade_stats(res.trades)
        assert ts["n_trades"] == 5
        assert ts["win_rate"] == pytest.approx(3 / 5)
        assert ts["best_trade"] == 300
        assert ts["worst_trade"] == -75
        assert ts["profit_factor"] == pytest.approx(600 / 125)
        assert ts["expectancy"] == pytest.approx(95.0)

    def test_regime_slice(self) -> None:
        res = self._build_result_with_known_pnls([100, 50, -25, 75, -10])
        rs = regime_slice(res.trades)
        assert rs.height == 2
        assert set(rs["quant_regime"].to_list()) == {"range_low", "range_medium"}

    def test_all_metrics_runs(self) -> None:
        res = self._build_result_with_known_pnls([100, -50])
        m = all_metrics(res, timeframe="5Min")
        assert "trade_stats" in m
        assert "equity_stats" in m
        assert "exit_reasons" in m
