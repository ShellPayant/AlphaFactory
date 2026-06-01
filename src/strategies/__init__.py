"""Strategy implementations.

Every strategy is a pair of (spec document + Strategy subclass). Specs live
in ``docs/strategies/``; the code lives here. Both must agree.
"""

from .base import Side, Signal, Strategy
from .bollinger_mr import BollingerMR
from .donchian_trend import DonchianTrend
from .five_day_reversal import FiveDayReversal
from .internal_bar_strength import InternalBarStrength
from .intraday_momentum_spy import IntradayMomentumSPY
from .monthly_momentum import MonthlyMomentum
from .range_mean_reversion import RangeMeanReversion
from .rsi2_pullback import RSI2Pullback
from .turn_of_month import TurnOfMonth

__all__ = [
    "BollingerMR",
    "DonchianTrend",
    "FiveDayReversal",
    "IntradayMomentumSPY",
    "InternalBarStrength",
    "MonthlyMomentum",
    "RangeMeanReversion",
    "RSI2Pullback",
    "Side",
    "Signal",
    "Strategy",
    "TurnOfMonth",
]
