"""Tests for ATR, ADX, and VWAP indicators."""

from __future__ import annotations

from datetime import datetime, timezone

import polars as pl
import pytest

from src.features.adx import adx
from src.features.atr import atr, true_range
from src.features.vwap import anchored_vwap, rolling_vwap, session_vwap


# =============================== ATR =================================


class TestATR:
    def test_appends_column_named_atr(self, trending_bars: pl.DataFrame) -> None:
        out = atr(trending_bars, period=14)
        assert "atr" in out.columns
        assert out.height == trending_bars.height

    def test_first_period_minus_one_are_null_wilder(
        self, trending_bars: pl.DataFrame
    ) -> None:
        out = atr(trending_bars, period=14, smoothing="wilder")
        first_valid = out["atr"].is_not_null().to_list().index(True)
        assert first_valid == 13  # period - 1

    def test_first_period_minus_one_are_null_sma(
        self, trending_bars: pl.DataFrame
    ) -> None:
        out = atr(trending_bars, period=14, smoothing="sma")
        first_valid = out["atr"].is_not_null().to_list().index(True)
        assert first_valid == 13

    def test_atr_is_positive(self, trending_bars: pl.DataFrame) -> None:
        out = atr(trending_bars, period=14)
        valid = out.drop_nulls("atr")
        assert (valid["atr"] > 0).all()

    def test_known_value_sma(self, make_bars: object) -> None:
        # Closes step by 1 each bar with spread=0.5. So each bar:
        # open = prev_close, close = open + 1
        # high = close + 0.5, low = open - 0.5
        # TR (bar T, T>=1) = max(high-low, |high-prev_close|, |low-prev_close|)
        #   high-low = (close+0.5) - (open-0.5) = 2.0
        #   high-prev_close = (close+0.5) - open = 1.5
        #   low-prev_close = open - 0.5 - open = -0.5 → abs = 0.5
        # → TR = 2.0
        closes = [100.0 + i for i in range(20)]
        df = make_bars(closes)  # type: ignore[operator]
        out = atr(df, period=5, smoothing="sma")
        # ATR at bar 4 (0-indexed): mean of first 5 TRs. TR[0] = high-low = 2.
        # TR[1..] = 2 as derived above. So ATR[4] = 2.0.
        assert out["atr"][4] == pytest.approx(2.0, abs=1e-9)

    def test_raises_on_short_period(self, trending_bars: pl.DataFrame) -> None:
        with pytest.raises(ValueError):
            atr(trending_bars, period=1)

    def test_raises_on_missing_columns(self) -> None:
        bad = pl.DataFrame({"ts": [datetime.now(timezone.utc)], "close": [1.0]})
        with pytest.raises(ValueError):
            atr(bad, period=14)


# ============================== True Range ============================


class TestTrueRange:
    def test_first_tr_is_high_minus_low(self, trending_bars: pl.DataFrame) -> None:
        tr = true_range(trending_bars)
        first_hl = trending_bars["high"][0] - trending_bars["low"][0]
        assert tr[0] == pytest.approx(first_hl)


# =============================== ADX ==================================


class TestADX:
    def test_appends_three_columns(self, trending_bars: pl.DataFrame) -> None:
        out = adx(trending_bars, period=14)
        for col in ("adx", "plus_di", "minus_di"):
            assert col in out.columns

    def test_adx_high_on_trending_data(self, trending_bars: pl.DataFrame) -> None:
        out = adx(trending_bars, period=14)
        # On a clean uptrend ADX should rise well above 25 by mid-series.
        late = out.tail(50).drop_nulls("adx")
        assert late["adx"].mean() > 30.0

    def test_adx_low_on_ranging_data(self, ranging_bars: pl.DataFrame) -> None:
        out = adx(ranging_bars, period=14)
        late = out.tail(50).drop_nulls("adx")
        assert late["adx"].mean() < 25.0

    def test_plus_di_dominates_in_uptrend(self, trending_bars: pl.DataFrame) -> None:
        out = adx(trending_bars, period=14)
        late = out.tail(50).drop_nulls("plus_di")
        assert (late["plus_di"] > late["minus_di"]).mean() > 0.7

    def test_adx_in_zero_to_hundred(self, trending_bars: pl.DataFrame) -> None:
        out = adx(trending_bars, period=14).drop_nulls("adx")
        assert (out["adx"] >= 0).all()
        assert (out["adx"] <= 100).all()

    def test_prefix_applied(self, trending_bars: pl.DataFrame) -> None:
        out = adx(trending_bars, period=14, column_prefix="h1_")
        assert "h1_adx" in out.columns
        assert "h1_plus_di" in out.columns


# =============================== VWAP =================================


class TestSessionVWAP:
    def test_appends_column(self, trending_bars: pl.DataFrame) -> None:
        out = session_vwap(trending_bars)
        assert "vwap" in out.columns

    def test_first_bar_equals_typical_price(self, trending_bars: pl.DataFrame) -> None:
        out = session_vwap(trending_bars)
        h, l, c = trending_bars["high"][0], trending_bars["low"][0], trending_bars["close"][0]
        expected = (h + l + c) / 3.0
        assert out["vwap"][0] == pytest.approx(expected, rel=1e-9)

    def test_vwap_bounded_by_session_range(self, trending_bars: pl.DataFrame) -> None:
        out = session_vwap(trending_bars)
        # In a single session, VWAP must lie within [session_low, session_high].
        sess_low = trending_bars["low"].min()
        sess_high = trending_bars["high"].max()
        valid = out.drop_nulls("vwap")
        assert (valid["vwap"] >= sess_low).all()
        assert (valid["vwap"] <= sess_high).all()

    def test_resets_across_sessions(self, make_bars: object) -> None:
        # Two sessions: a flat one at 100 and the next at 200.
        from datetime import timedelta

        day1_start = datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc)  # 09:30 ET
        day2_start = day1_start + timedelta(days=1)
        closes = [100.0] * 10 + [200.0] * 10
        ts = [day1_start + timedelta(minutes=5 * i) for i in range(10)] + [
            day2_start + timedelta(minutes=5 * i) for i in range(10)
        ]
        df = pl.DataFrame(
            {
                "ts": ts,
                "open": closes,
                "high": [c + 0.5 for c in closes],
                "low": [c - 0.5 for c in closes],
                "close": closes,
                "volume": [1000.0] * 20,
            }
        )
        out = session_vwap(df)
        # First bar of day 2 should reset → VWAP near 200, not blended with day 1.
        assert out["vwap"][10] == pytest.approx(200.0, abs=1.0)


class TestAnchoredVWAP:
    def test_null_before_anchor(self, trending_bars: pl.DataFrame) -> None:
        anchor = trending_bars["ts"][50]
        out = anchored_vwap(trending_bars, anchor=anchor)
        assert out["avwap"][:50].null_count() == 50
        assert out["avwap"][50] is not None

    def test_bounded_by_post_anchor_range(self, trending_bars: pl.DataFrame) -> None:
        anchor = trending_bars["ts"][100]
        out = anchored_vwap(trending_bars, anchor=anchor)
        post = trending_bars.tail(trending_bars.height - 100)
        valid = out.drop_nulls("avwap")
        assert valid["avwap"].min() >= post["low"].min()
        assert valid["avwap"].max() <= post["high"].max()


class TestRollingVWAP:
    def test_appends_column(self, trending_bars: pl.DataFrame) -> None:
        out = rolling_vwap(trending_bars, window=20)
        assert "rvwap" in out.columns

    def test_first_window_minus_one_null(self, trending_bars: pl.DataFrame) -> None:
        out = rolling_vwap(trending_bars, window=20)
        first_valid = out["rvwap"].is_not_null().to_list().index(True)
        assert first_valid == 19

    def test_invalid_window_raises(self, trending_bars: pl.DataFrame) -> None:
        with pytest.raises(ValueError):
            rolling_vwap(trending_bars, window=1)
