"""Symbol universe definitions for the autonomous search engine.

Tiered universe so we can:

* TIER_0_SMOKE — handful of ETFs for end-to-end smoke tests (~6 names).
* TIER_1_CORE_ETFS — broad market + sector + factor ETFs (~30 names).
* TIER_2_LARGE_CAPS — TIER_1 plus mega-cap US singles (~80 names).
* TIER_3_BROAD — full top-200ish liquid US equity research universe (~210 names).

Design notes:

* US equities only (per project scope memory).
* Curated by liquidity (ADV) + sector coverage. No microcaps, no biotech
  binary-event names, no recent IPOs without enough history. These cause
  more backtest noise than they're worth — easier to add them deliberately
  later than to filter them out of a noisy backtest.
* Sector coverage spans all 11 GICS sectors. The factor-ETF block lets
  cross-sectional / sector-rotation strategies have something to rank
  without needing per-stock fundamentals.
* No leveraged or inverse ETFs (TQQQ/SQQQ/etc.). They distort vol-targeted
  position sizing in counterintuitive ways and aren't core research surface.
* ADRs included where the underlying is genuinely liquid in NY hours
  (TSM, ASML, BABA-class). Otherwise skipped.

When the data layer is on Polygon/Massive, the survivorship-bias-free version
of TIER_3 should be derived dynamically from the historical ticker reference
endpoint, including delisted names that were liquid at the time. For now,
this is the live-as-of-2026 universe.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Tier 0 — smoke test universe
# ---------------------------------------------------------------------------
TIER_0_SMOKE: tuple[str, ...] = (
    "SPY", "QQQ", "IWM", "XLF", "XLK", "TLT",
)

# ---------------------------------------------------------------------------
# Tier 1 — core ETFs (broad market, sector SPDRs, factor, international, macro)
# ---------------------------------------------------------------------------
BROAD_MARKET_ETFS: tuple[str, ...] = (
    "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO",
)

SECTOR_SPDR_ETFS: tuple[str, ...] = (
    "XLF",   # Financials
    "XLK",   # Technology
    "XLE",   # Energy
    "XLV",   # Health Care
    "XLI",   # Industrials
    "XLY",   # Consumer Discretionary
    "XLP",   # Consumer Staples
    "XLU",   # Utilities
    "XLB",   # Materials
    "XLRE",  # Real Estate
    "XLC",   # Communication Services
)

FACTOR_ETFS: tuple[str, ...] = (
    "MTUM",  # Momentum
    "QUAL",  # Quality
    "VLUE",  # Value
    "USMV",  # Min Vol
    "SIZE",  # Size
    "VTV",   # Vanguard Value
    "VUG",   # Vanguard Growth
    "VYM",   # High Dividend Yield
    "SPLV",  # S&P 500 Low Vol
)

INTERNATIONAL_ETFS: tuple[str, ...] = (
    "EFA", "IEFA", "EEM", "VWO", "FXI", "EWJ", "EWZ", "INDA",
)

MACRO_HEDGE_ETFS: tuple[str, ...] = (
    "TLT",   # Long-term Treasuries
    "IEF",   # 7-10y Treasuries
    "HYG",   # High-yield credit
    "LQD",   # IG credit
    "GLD",   # Gold
    "SLV",   # Silver
    "UUP",   # USD index
)

TIER_1_CORE_ETFS: tuple[str, ...] = tuple(dict.fromkeys(
    BROAD_MARKET_ETFS
    + SECTOR_SPDR_ETFS
    + FACTOR_ETFS
    + INTERNATIONAL_ETFS
    + MACRO_HEDGE_ETFS
))

# ---------------------------------------------------------------------------
# Tier 2 — mega-cap US singles spanning all 11 GICS sectors
# ---------------------------------------------------------------------------
MEGA_CAP_TECH: tuple[str, ...] = (
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "META", "AMZN", "TSLA",
    "AVGO", "ORCL", "ADBE", "CRM", "CSCO", "ACN", "NFLX", "AMD",
    "INTC", "QCOM", "TXN", "INTU", "IBM", "AMAT", "MU", "LRCX", "KLAC",
)

MEGA_CAP_FINANCIALS: tuple[str, ...] = (
    "BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "AXP", "BLK",
    "SCHW", "C", "USB", "PNC", "TFC", "CB", "MMC", "SPGI", "ICE", "CME",
)

MEGA_CAP_HEALTH: tuple[str, ...] = (
    "UNH", "JNJ", "LLY", "ABBV", "MRK", "TMO", "ABT", "PFE", "DHR",
    "BMY", "AMGN", "CVS", "MDT", "ISRG", "GILD", "ELV", "VRTX", "REGN",
)

MEGA_CAP_CONSUMER: tuple[str, ...] = (
    "WMT", "HD", "COST", "PG", "KO", "PEP", "MCD", "NKE", "SBUX", "LOW",
    "TGT", "DIS", "BKNG", "MAR", "CMG", "TJX", "MO", "PM", "MDLZ",
)

MEGA_CAP_INDUSTRIAL: tuple[str, ...] = (
    "GE", "CAT", "HON", "UPS", "BA", "RTX", "DE", "LMT", "UNP", "NOC",
    "GD", "MMM", "ETN", "EMR", "WM", "CSX", "NSC", "ITW",
)

MEGA_CAP_ENERGY: tuple[str, ...] = (
    "XOM", "CVX", "COP", "EOG", "SLB", "PSX", "MPC", "OXY", "PXD",
)

MEGA_CAP_UTILITIES_MATERIALS_REALESTATE: tuple[str, ...] = (
    "NEE", "DUK", "SO", "AEP", "D",                    # Utilities
    "LIN", "APD", "SHW", "FCX", "NEM",                  # Materials
    "PLD", "AMT", "EQIX", "CCI", "PSA", "O",            # Real Estate
)

MEGA_CAP_COMMS: tuple[str, ...] = (
    "T", "VZ", "TMUS", "CMCSA", "CHTR",
)

LIQUID_GROWTH_NAMES: tuple[str, ...] = (
    # Newer / higher-vol names that still have multi-year clean histories
    "UBER", "ABNB", "PYPL", "SQ", "SHOP", "PLTR", "SNOW", "NET", "CRWD",
    "ZS", "DDOG", "MDB", "OKTA", "PANW", "FTNT", "MRVL", "ON", "ARM",
    "COIN", "HOOD", "SOFI", "RBLX", "U", "SNAP", "PINS", "ROKU", "SPOT",
    "DASH", "RIVN", "LCID", "F", "GM",
)

LIQUID_ADRS: tuple[str, ...] = (
    "TSM", "ASML", "BABA", "JD", "PDD", "BIDU", "NIO",
    "SAP", "TM", "NVO", "AZN", "SHEL", "BP",
)

TIER_2_MEGA_CAPS: tuple[str, ...] = tuple(dict.fromkeys(
    TIER_1_CORE_ETFS
    + MEGA_CAP_TECH
    + MEGA_CAP_FINANCIALS
    + MEGA_CAP_HEALTH
    + MEGA_CAP_CONSUMER
    + MEGA_CAP_INDUSTRIAL
    + MEGA_CAP_ENERGY
    + MEGA_CAP_UTILITIES_MATERIALS_REALESTATE
    + MEGA_CAP_COMMS
))

# ---------------------------------------------------------------------------
# Tier 3 — broad research universe (~210 names)
# ---------------------------------------------------------------------------
TIER_3_BROAD: tuple[str, ...] = tuple(dict.fromkeys(
    TIER_2_MEGA_CAPS
    + LIQUID_GROWTH_NAMES
    + LIQUID_ADRS
))


# ---------------------------------------------------------------------------
# Lookup helper
# ---------------------------------------------------------------------------
UNIVERSES: dict[str, tuple[str, ...]] = {
    "tier0_smoke": TIER_0_SMOKE,
    "tier1_core_etfs": TIER_1_CORE_ETFS,
    "tier2_mega_caps": TIER_2_MEGA_CAPS,
    "tier3_broad": TIER_3_BROAD,
}


def get_universe(name: str) -> tuple[str, ...]:
    """Return the symbol tuple for a named universe tier.

    Raises ``KeyError`` with the list of valid names on bad input.
    """
    if name not in UNIVERSES:
        raise KeyError(
            f"Unknown universe '{name}'. Valid: {sorted(UNIVERSES.keys())}"
        )
    return UNIVERSES[name]


def universe_size(name: str) -> int:
    return len(get_universe(name))
