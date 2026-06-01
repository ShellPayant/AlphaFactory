"""No-lookahead tests — the most important tests in Sprint 1.

A lookahead bug is when an indicator (or strategy) silently uses information
from a *future* bar to compute its value at the current bar. These bugs make
backtests look spectacular and live trading lose money.

The general technique: compute an indicator on the full series, then compute
it again on a truncated copy that ends at bar T, and assert the value at
bar T matches. If it doesn't, the function is using future data.

We test this for ATR, ADX, VWAP, anchored VWAP, and both regime classifiers.
"""

from __future__ import annotations

import polars as pl
import pytest

from src.features.adx import adx
from src.features.atr import atr
from src.features.vwap import anchored_vwap, session_vwap
from src.regimes.regime_classifier import (
    add_categorical_state,
    add_quant_regime,
    classify_regimes,
)


def _assert_prefix_invariant(
    full: pl.DataFrame,
    df: pl.DataFrame,
    fn,
    cols: list[str],
    *,
    cut_at: int = 150,
    cut_to: int = 200,
) -> None:
    """Assert that fn(df[:N]) matches fn(df)[:N] for several N values.

    This is the core no-lookahead property: extending the future must not
    change the past.
    """
    for n in range(cut_at, cut_to + 1, 10):
        truncated = fn(df.head(n))
        for col in cols:
            full_vals = full[col].head(n).to_list()
            trunc_vals = truncated[col].to_list()
            for i, (f, t) in enumerate(zip(full_vals, trunc_vals)):
                if f is None and t is None:
                    continue
                if f is None or t is None:
                    raise AssertionError(
                        f"{fn.__name__}[{col}] differs at i={i}, n={n}: "
                        f"full={f!r} trunc={t!r}"
                    )
                assert pytest.approx(f, rel=1e-9, abs=1e-9) == t, (
                    f"{fn.__name__}[{col}] differs at i={i}, n={n}: "
                    f"full={f} trunc={t}"
                )


class TestATRNoLookahead:
    def test_wilder(self, trending_bars: pl.DataFrame) -> None:
        full = atr(trending_bars, period=14, smoothing="wilder")
        _assert_prefix_invariant(
            full, trending_bars, lambda d: atr(d, period=14, smoothing="wilder"), ["atr"]
        )

    def test_sma(self, trending_bars: pl.DataFrame) -> None:
        full = atr(trending_bars, period=14, smoothing="sma")
        _assert_prefix_invariant(
            full, trending_bars, lambda d: atr(d, period=14, smoothing="sma"), ["atr"]
        )


class TestADXNoLookahead:
    def test_adx_components(self, trending_bars: pl.DataFrame) -> None:
        full = adx(trending_bars, period=14)
        _assert_prefix_invariant(
            full,
            trending_bars,
            lambda d: adx(d, period=14),
            ["adx", "plus_di", "minus_di"],
        )


class TestVWAPNoLookahead:
    def test_session_vwap(self, trending_bars: pl.DataFrame) -> None:
        full = session_vwap(trending_bars)
        _assert_prefix_invariant(full, trending_bars, session_vwap, ["vwap"])

    def test_anchored_vwap(self, trending_bars: pl.DataFrame) -> None:
        anchor = trending_bars["ts"][20]
        full = anchored_vwap(trending_bars, anchor=anchor)
        _assert_prefix_invariant(
            full, trending_bars, lambda d: anchored_vwap(d, anchor=anchor), ["avwap"]
        )


class TestRegimeNoLookahead:
    """The regime classifier is the integration point — most likely to leak."""

    def test_quant_regime(self, trending_bars: pl.DataFrame) -> None:
        full = add_quant_regime(trending_bars)
        _assert_prefix_invariant(
            full,
            trending_bars,
            add_quant_regime,
            ["adx", "atr", "trend_bucket", "vol_bucket", "quant_regime"],
            cut_at=120,
        )

    def test_categorical_state(self, ranging_bars: pl.DataFrame) -> None:
        full = add_categorical_state(ranging_bars)
        _assert_prefix_invariant(
            full,
            ranging_bars,
            add_categorical_state,
            ["atr", "categorical_state"],
            cut_at=120,
        )

    def test_full_pipeline(self, trending_bars: pl.DataFrame) -> None:
        full = classify_regimes(trending_bars)
        _assert_prefix_invariant(
            full,
            trending_bars,
            classify_regimes,
            ["adx", "atr", "trend_bucket", "vol_bucket", "quant_regime", "categorical_state"],
            cut_at=120,
        )
