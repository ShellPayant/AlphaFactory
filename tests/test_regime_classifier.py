"""Tests for the regime classifier — quant grid and categorical state."""

from __future__ import annotations

import polars as pl

from src.regimes.regime_classifier import (
    RegimeConfig,
    add_categorical_state,
    add_quant_regime,
    classify_regimes,
)


class TestQuantRegime:
    def test_columns_added(self, trending_bars: pl.DataFrame) -> None:
        out = add_quant_regime(trending_bars)
        for col in ("adx", "atr", "trend_bucket", "vol_bucket", "quant_regime"):
            assert col in out.columns

    def test_trend_bucket_values(self, trending_bars: pl.DataFrame) -> None:
        out = add_quant_regime(trending_bars).drop_nulls("trend_bucket")
        assert set(out["trend_bucket"].unique().to_list()).issubset(
            {"range", "weak_trend", "strong_trend"}
        )

    def test_vol_bucket_values(self, trending_bars: pl.DataFrame) -> None:
        out = add_quant_regime(trending_bars).drop_nulls("vol_bucket")
        assert set(out["vol_bucket"].unique().to_list()).issubset({"low", "medium", "high"})

    def test_uptrend_classified_as_trending(self, trending_bars: pl.DataFrame) -> None:
        out = add_quant_regime(trending_bars).drop_nulls("trend_bucket").tail(50)
        # On a clean uptrend, most of the late bars should be weak or strong trend.
        trending_frac = out.filter(pl.col("trend_bucket") != "range").height / out.height
        assert trending_frac > 0.7

    def test_ranging_classified_as_range(self, ranging_bars: pl.DataFrame) -> None:
        out = add_quant_regime(ranging_bars).drop_nulls("trend_bucket").tail(50)
        range_frac = out.filter(pl.col("trend_bucket") == "range").height / out.height
        assert range_frac > 0.7

    def test_quant_regime_is_concatenation(self, trending_bars: pl.DataFrame) -> None:
        out = add_quant_regime(trending_bars).drop_nulls("quant_regime").tail(10)
        for row in out.iter_rows(named=True):
            assert row["quant_regime"] == f"{row['trend_bucket']}_{row['vol_bucket']}"


class TestCategoricalState:
    def test_column_added(self, trending_bars: pl.DataFrame) -> None:
        out = add_categorical_state(trending_bars)
        assert "categorical_state" in out.columns

    def test_state_values(self, trending_bars: pl.DataFrame) -> None:
        out = add_categorical_state(trending_bars)
        assert set(out["categorical_state"].unique().to_list()).issubset(
            {"consolidating", "directional", "chaotic"}
        )

    def test_uptrend_mostly_directional(self, trending_bars: pl.DataFrame) -> None:
        out = add_categorical_state(trending_bars).tail(150)
        directional_frac = (
            out.filter(pl.col("categorical_state") == "directional").height / out.height
        )
        # A clean linear uptrend should be flagged directional most of the time
        # after the warm-up window.
        assert directional_frac > 0.6

    def test_ranging_mostly_consolidating(self, ranging_bars: pl.DataFrame) -> None:
        out = add_categorical_state(ranging_bars).tail(150)
        consolidating_frac = (
            out.filter(pl.col("categorical_state") == "consolidating").height / out.height
        )
        assert consolidating_frac > 0.5

    def test_chaotic_data_mostly_chaotic(self, chaotic_bars: pl.DataFrame) -> None:
        out = add_categorical_state(chaotic_bars).tail(100)
        chaotic_frac = (
            out.filter(pl.col("categorical_state") == "chaotic").height / out.height
        )
        # Growing-volatility chaotic series should not be tagged consolidating
        # or steadily directional most of the time.
        assert chaotic_frac > 0.3


class TestClassifyRegimes:
    def test_runs_both(self, trending_bars: pl.DataFrame) -> None:
        out = classify_regimes(trending_bars)
        for col in (
            "adx",
            "atr",
            "trend_bucket",
            "vol_bucket",
            "quant_regime",
            "categorical_state",
        ):
            assert col in out.columns

    def test_custom_config_applied(self, trending_bars: pl.DataFrame) -> None:
        cfg = RegimeConfig(adx_range_max=50.0, adx_strong_min=99.0)
        out = classify_regimes(trending_bars, cfg=cfg).drop_nulls("trend_bucket")
        # With absurdly high thresholds, basically everything is "range".
        range_frac = out.filter(pl.col("trend_bucket") == "range").height / out.height
        assert range_frac > 0.9
