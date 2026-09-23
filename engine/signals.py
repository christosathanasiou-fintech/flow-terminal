"""
engine/signals.py — Generates "setups" (LONG / SHORT / WAIT) per asset.

Rules (rule-based and transparent — not a black box):
  • Trend filter: price vs SMA20/SMA50, SMA20 vs SMA50
  • Momentum: RSI(14) — avoid LONG at RSI>75 and SHORT at RSI<25
  • Volatility: ATR(14) for the stop (2×ATR) and target (3×ATR) → R:R = 1.5
  • Volume: confirmation if 5d volume > 20d volume
  • Rotation: the score from the rotation engine (if given) is added to the
    conviction

Output per asset: direction, conviction (0-100), entry, stop, target, rr,
rsi, atr, rationale (list of short plain-English reasons).

Upgrade path:
  - Backtest the rules with vectorbt/backtrader and show the hit-rate per
    asset class in the UI (this is what makes a portfolio project stand out).
  - Add multi-timeframe confirmation (4h + 1d) before giving conviction > 70.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class Setup:
    ticker: str
    direction: str            # LONG / SHORT / WAIT
    conviction: int           # 0..100
    entry: float
    stop: float
    target: float
    rr: float
    rsi: float
    atr: float
    atr_pct: float
    trend: str                # UPTREND / DOWNTREND / SIDEWAYS
    rationale: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def rsi(series: pd.Series, n: int = 14) -> float:
    d = series.diff().dropna()
    if len(d) < n + 1:
        return 50.0
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    val = 100 - 100 / (1 + rs)
    return float(val.iloc[-1]) if not np.isnan(val.iloc[-1]) else 50.0


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> float:
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    val = tr.ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
    return float(val) if not np.isnan(val) else float(close.iloc[-1] * 0.02)


def build_setup(ticker: str, ohlc: pd.DataFrame, rotation_score: float | None = None) -> Setup | None:
    """
    ohlc: DataFrame with Open/High/Low/Close/Volume columns (daily, ≥ 30 rows).
    """
    ohlc = ohlc.dropna(subset=["Close"])
    if len(ohlc) < 30:
        return None
    c, h, l = ohlc["Close"], ohlc["High"].fillna(ohlc["Close"]), ohlc["Low"].fillna(ohlc["Close"])
    v = ohlc["Volume"].fillna(0) if "Volume" in ohlc else pd.Series(0, index=c.index)
    last = float(c.iloc[-1])
    sma20, sma50 = float(c.tail(20).mean()), float(c.tail(50).mean()) if len(c) >= 50 else float(c.tail(20).mean())
    r = rsi(c)
    a = atr(h, l, c)
    a_pct = a / last * 100
    vol_ok = float(v.tail(5).mean()) > float(v.tail(20).mean()) if v.sum() > 0 else None

    # --- Trend ------------------------------------------------------------
    pts = (last > sma20) + (last > sma50) + (sma20 > sma50)
    if pts == 3:
        trend = "UPTREND"
    elif pts == 0:
        trend = "DOWNTREND"
    else:
        trend = "SIDEWAYS"

    why: list[str] = []
    score = 0
    if trend == "UPTREND":
        score += 35; why.append("price above SMA20 & SMA50, SMA20 > SMA50")
    elif trend == "DOWNTREND":
        score -= 35; why.append("price below SMA20 & SMA50, SMA20 < SMA50")
    else:
        why.append("mixed moving-average picture (sideways)")

    # --- Momentum ---------------------------------------------------------
    if 50 < r < 70:
        score += 15; why.append(f"RSI {r:.0f}: healthy upside momentum")
    elif 30 < r <= 50:
        score -= 15; why.append(f"RSI {r:.0f}: weak momentum")
    elif r >= 75:
        score -= 10; why.append(f"RSI {r:.0f}: overbought — chase risk")
    elif r <= 25:
        score += 10; why.append(f"RSI {r:.0f}: oversold — possible bounce")

    # --- Volume -----------------------------------------------------------
    if vol_ok is True:
        score += 10 * (1 if score >= 0 else -1); why.append("5d volume > 20d volume (confirmation)")
    elif vol_ok is False:
        why.append("volume below average — no confirmation")

    # --- Rotation ---------------------------------------------------------
    if rotation_score is not None and not np.isnan(rotation_score):
        score += float(rotation_score) * 0.3
        why.append(f"rotation score {rotation_score:+.0f} "
                   f"(capital {'inflow' if rotation_score > 0 else 'outflow'})")

    # --- Decision ---------------------------------------------------------
    conviction = int(min(100, abs(score)))
    if score >= 25:
        direction, stop, target = "LONG", last - 2 * a, last + 3 * a
    elif score <= -25:
        direction, stop, target = "SHORT", last + 2 * a, last - 3 * a
    else:
        direction, stop, target = "WAIT", last - 2 * a, last + 3 * a
        why.append("no clear edge — wait for confirmation")

    return Setup(ticker=ticker, direction=direction, conviction=conviction,
                 entry=round(last, 4), stop=round(stop, 4), target=round(target, 4),
                 rr=1.5, rsi=round(r, 1), atr=round(a, 4), atr_pct=round(a_pct, 2),
                 trend=trend, rationale=why)


def build_setups(hist: pd.DataFrame, tickers: list[str],
                 rotation: pd.DataFrame | None = None) -> list[Setup]:
    out = []
    for t in tickers:
        try:
            ohlc = hist[t]
        except KeyError:
            continue
        rs = None
        if rotation is not None and t in rotation.index:
            rs = float(rotation.loc[t, "score"])
        s = build_setup(t, ohlc, rs)
        if s:
            out.append(s)
    return sorted(out, key=lambda s: (s.direction == "WAIT", -s.conviction))
