"""Regime classification — quant (ADX×ATR grid), categorical (state), macro (vol)."""

from .macro_regime import (
    MacroRegimeConfig,
    VolRegime,
    attach_vol_regime_to_bars,
    classify_volatility_regime,
    latest_regime,
)
from .regime_classifier import (
    CategoricalState,
    RegimeConfig,
    TrendBucket,
    VolBucket,
    add_categorical_state,
    add_quant_regime,
    classify_regimes,
)

__all__ = [
    "CategoricalState",
    "MacroRegimeConfig",
    "RegimeConfig",
    "TrendBucket",
    "VolBucket",
    "VolRegime",
    "add_categorical_state",
    "add_quant_regime",
    "attach_vol_regime_to_bars",
    "classify_regimes",
    "classify_volatility_regime",
    "latest_regime",
]
