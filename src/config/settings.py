"""Strongly-typed runtime settings, loaded from .env + environment.

Use as::

    from src.config.settings import get_settings
    s = get_settings()
    s.alpaca_api_key  # → "PK..."

Settings are cached per-process; importable from any module without paying
the parsing cost more than once.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Mode = Literal["research", "paper", "live"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Data providers ---
    polygon_api_key: str = Field(default="", alias="POLYGON_API_KEY")

    # --- Alpaca (paper) ---
    alpaca_api_key: str = Field(default="", alias="ALPACA_API_KEY")
    alpaca_secret_key: str = Field(default="", alias="ALPACA_SECRET_KEY")
    alpaca_base_url: str = Field(
        default="https://paper-api.alpaca.markets", alias="ALPACA_BASE_URL"
    )

    # --- Alpaca (live) — intentionally absent from research/paper mode use ---
    alpaca_live_api_key: str = Field(default="", alias="ALPACA_LIVE_API_KEY")
    alpaca_live_secret_key: str = Field(default="", alias="ALPACA_LIVE_SECRET_KEY")
    alpaca_live_base_url: str = Field(
        default="https://api.alpaca.markets", alias="ALPACA_LIVE_BASE_URL"
    )

    # --- Risk policy overrides ---
    alpha_max_risk_per_trade: float = Field(default=0.0025, alias="ALPHA_MAX_RISK_PER_TRADE")
    alpha_max_daily_loss: float = Field(default=0.01, alias="ALPHA_MAX_DAILY_LOSS")
    alpha_max_weekly_loss: float = Field(default=0.025, alias="ALPHA_MAX_WEEKLY_LOSS")
    alpha_max_open_positions: int = Field(default=1, alias="ALPHA_MAX_OPEN_POSITIONS")
    alpha_max_correlated_positions: int = Field(
        default=2, alias="ALPHA_MAX_CORRELATED_POSITIONS"
    )

    # --- Mode + kill switch ---
    alpha_mode: Mode = Field(default="research", alias="ALPHA_MODE")
    alpha_kill_switch_enabled: bool = Field(default=True, alias="ALPHA_KILL_SWITCH_ENABLED")

    # --- Paths ---
    alpha_data_root: Path = Field(default=Path("./data"), alias="ALPHA_DATA_ROOT")
    alpha_log_root: Path = Field(default=Path("./logs"), alias="ALPHA_LOG_ROOT")

    # --- Logging ---
    alpha_log_level: str = Field(default="INFO", alias="ALPHA_LOG_LEVEL")

    # ------------- Validators / helpers -------------

    @field_validator("alpha_max_risk_per_trade")
    @classmethod
    def _risk_per_trade_sane(cls, v: float) -> float:
        if not 0 < v <= 0.05:
            raise ValueError(
                f"ALPHA_MAX_RISK_PER_TRADE={v} is outside the sane range (0, 0.05]. "
                "If you really mean to risk > 5% per trade, edit this validator."
            )
        return v

    @field_validator("alpha_mode")
    @classmethod
    def _mode_lower(cls, v: str) -> str:
        return v.lower()  # type: ignore[return-value]

    def require_alpaca_paper_keys(self) -> None:
        """Call before using the Alpaca client. Raises with a friendly message."""
        missing = [
            name
            for name, val in [
                ("ALPACA_API_KEY", self.alpaca_api_key),
                ("ALPACA_SECRET_KEY", self.alpaca_secret_key),
            ]
            if not val
        ]
        if missing:
            raise RuntimeError(
                f"Missing Alpaca credentials: {', '.join(missing)}. "
                "Sign up free at https://alpaca.markets/sign-up (paper account), "
                "then paste the keys into your .env file."
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached, process-wide Settings instance."""
    return Settings()  # type: ignore[call-arg]
