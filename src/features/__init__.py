"""Indicator library — pure-Polars, no-lookahead.

Every function in this package takes a sorted UTC OHLCV DataFrame and
returns the same frame with one or more appended columns. Functions are
pure and unit-tested; they do not touch I/O.
"""

from .adx import adx
from .atr import atr, true_range
from .vwap import anchored_vwap, rolling_vwap, session_vwap

__all__ = [
    "adx",
    "anchored_vwap",
    "atr",
    "rolling_vwap",
    "session_vwap",
    "true_range",
]
