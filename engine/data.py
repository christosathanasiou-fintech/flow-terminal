"""
engine/data.py — Data sources for FLOW TERMINAL.

Every function is "safe": on a network failure it returns an empty
DataFrame/list instead of raising, so the UI never crashes.

Sources (all free, no API key):
  • yfinance      → stocks, indices, ETFs, commodity futures, FX, bonds
                    (US equities ~15-min delay, futures/FX near real-time)
  • CoinGecko     → top-100 crypto, trending (real-time, rate limit ~30 req/min)
  • DexScreener   → new tokens, boosted tokens, on-chain pair data (real-time)
  • GoPlus        → token security for EVM chains (honeypot, mintable, tax)
  • RugCheck      → token security for Solana

Upgrade path:
  - True real-time US equities: replace fetch_history with a
    Polygon.io / Alpaca websocket (both have a free tier).
  - Real ETF flows (actual creations/redemptions instead of a proxy): ETF.com or
    Bloomberg — there is no free API, so this module uses a proxy
    (dollar volume × direction).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
import requests

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None

HTTP_TIMEOUT = 12
UA = {"User-Agent": "flow-terminal/1.0 (educational)"}


# --------------------------------------------------------------------------- #
# MARKET UNIVERSE
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Asset:
    ticker: str          # yfinance symbol
    name: str            # display name
    short: str           # short label (GOLD, WTI, ...)
    group: str           # group: METALS / ENERGY / AGRICULTURE / INDICES / ...
    asset_class: str     # commodity / equity / index / fx / bond
    region: str = ""     # for the globe (market centre)
    lat: float = 0.0
    lon: float = 0.0


# --- Commodities (continuous front-month futures on yfinance) --------------
COMMODITIES: list[Asset] = [
    Asset("GC=F", "GOLD", "GOLD", "METALS", "commodity"),
    Asset("SI=F", "SILVER", "SILVER", "METALS", "commodity"),
    Asset("HG=F", "COPPER", "COPPER", "METALS", "commodity"),
    Asset("PL=F", "PLATINUM", "PLATINUM", "METALS", "commodity"),
    Asset("PA=F", "PALLADIUM", "PALLADIUM", "METALS", "commodity"),
    Asset("CL=F", "WTI OIL", "WTI", "ENERGY", "commodity"),
    Asset("BZ=F", "BRENT", "BRENT", "ENERGY", "commodity"),
    Asset("NG=F", "NAT GAS", "NATGAS", "ENERGY", "commodity"),
    Asset("RB=F", "GASOLINE", "RBOB", "ENERGY", "commodity"),
    Asset("HO=F", "HEATING OIL", "HEATOIL", "ENERGY", "commodity"),
    Asset("ZW=F", "WHEAT", "WHEAT", "AGRICULTURE", "commodity"),
    Asset("ZC=F", "CORN", "CORN", "AGRICULTURE", "commodity"),
    Asset("ZS=F", "SOYBEANS", "SOYBEANS", "AGRICULTURE", "commodity"),
    Asset("KC=F", "COFFEE", "COFFEE", "AGRICULTURE", "commodity"),
    Asset("SB=F", "SUGAR", "SUGAR", "AGRICULTURE", "commodity"),
    Asset("CC=F", "COCOA", "COCOA", "AGRICULTURE", "commodity"),
    Asset("CT=F", "COTTON", "COTTON", "AGRICULTURE", "commodity"),
    Asset("OJ=F", "ORANGE JUICE", "OJ", "AGRICULTURE", "commodity"),
    Asset("LE=F", "LIVE CATTLE", "CATTLE", "AGRICULTURE", "commodity"),
    Asset("HE=F", "LEAN HOGS", "HOGS", "AGRICULTURE", "commodity"),
]

# --- Market centres for the globe (country ETF as proxy for each market) ----
REGIONS: list[Asset] = [
    Asset("SPY", "NEW YORK", "NY", "CENTRES", "index", "New York", 40.71, -74.01),
    Asset("EWU", "LONDON", "LONDON", "CENTRES", "index", "London", 51.51, -0.13),
    Asset("EWG", "FRANKFURT", "DAX", "CENTRES", "index", "Frankfurt", 50.11, 8.68),
    Asset("EWQ", "PARIS", "PARIS", "CENTRES", "index", "Paris", 48.86, 2.35),
    Asset("EWJ", "TOKYO", "TOKYO", "CENTRES", "index", "Tokyo", 35.68, 139.69),
    Asset("MCHI", "SHANGHAI", "SHANGHAI", "CENTRES", "index", "Shanghai", 31.23, 121.47),
    Asset("EWH", "HONG KONG", "HK", "CENTRES", "index", "Hong Kong", 22.32, 114.17),
    Asset("INDA", "MUMBAI", "MUMBAI", "CENTRES", "index", "Mumbai", 19.08, 72.88),
    Asset("EWY", "SEOUL", "SEOUL", "CENTRES", "index", "Seoul", 37.57, 126.98),
    Asset("EWT", "TAIPEI", "TAIPEI", "CENTRES", "index", "Taipei", 25.03, 121.57),
    Asset("EWA", "SYDNEY", "SYDNEY", "CENTRES", "index", "Sydney", -33.87, 151.21),
    Asset("EWZ", "SAO PAULO", "SAOPAULO", "CENTRES", "index", "Sao Paulo", -23.55, -46.63),
    Asset("EWC", "TORONTO", "TORONTO", "CENTRES", "index", "Toronto", 43.65, -79.38),
    Asset("EWW", "MEXICO CITY", "MEXICO", "CENTRES", "index", "Mexico City", 19.43, -99.13),
    Asset("KSA", "RIYADH", "RIYADH", "CENTRES", "index", "Riyadh", 24.71, 46.68),
    Asset("UAE", "DUBAI", "DUBAI", "CENTRES", "index", "Dubai", 25.20, 55.27),
    Asset("EZA", "JOHANNESBURG", "JOBURG", "CENTRES", "index", "Johannesburg", -26.20, 28.04),
    Asset("GREK", "ATHENS", "ATHENS", "CENTRES", "index", "Athens", 37.98, 23.73),
]

# --- Asset classes for capital-rotation analysis ---------------------------
ASSET_CLASSES: list[Asset] = [
    Asset("SPY", "US EQUITIES", "US EQ", "CLASSES", "equity"),
    Asset("QQQ", "TECHNOLOGY", "TECH", "CLASSES", "equity"),
    Asset("IWM", "SMALL CAPS", "SMALL", "CLASSES", "equity"),
    Asset("EFA", "DEVELOPED ex-US", "DM", "CLASSES", "equity"),
    Asset("EEM", "EMERGING MKTS", "EM", "CLASSES", "equity"),
    Asset("TLT", "BONDS 20Y", "BONDS", "CLASSES", "bond"),
    Asset("GLD", "GOLD (ETF)", "GOLD", "CLASSES", "commodity"),
    Asset("USO", "OIL (ETF)", "OIL", "CLASSES", "commodity"),
    Asset("DBA", "AGRICULTURE (ETF)", "AGRI", "CLASSES", "commodity"),
    Asset("UUP", "US DOLLAR", "USD", "CLASSES", "fx"),
    Asset("BITO", "CRYPTO (ETF)", "CRYPTO", "CLASSES", "crypto"),
]

# --- S&P 500 sectors ---------------------------------------------------------
SECTORS: list[Asset] = [
    Asset("XLK", "TECHNOLOGY", "TECH", "SECTORS", "equity"),
    Asset("XLF", "FINANCIALS", "FIN", "SECTORS", "equity"),
    Asset("XLE", "ENERGY", "ENERGY", "SECTORS", "equity"),
    Asset("XLV", "HEALTH CARE", "HEALTH", "SECTORS", "equity"),
    Asset("XLY", "CONS. DISCRETIONARY", "DISCR", "SECTORS", "equity"),
    Asset("XLP", "CONS. STAPLES", "STAPLES", "SECTORS", "equity"),
    Asset("XLI", "INDUSTRIALS", "INDU", "SECTORS", "equity"),
    Asset("XLU", "UTILITIES", "UTIL", "SECTORS", "equity"),
    Asset("XLB", "MATERIALS", "MATER", "SECTORS", "equity"),
    Asset("XLRE", "REAL ESTATE", "REIT", "SECTORS", "equity"),
    Asset("XLC", "COMMUNICATIONS", "COMM", "SECTORS", "equity"),
    Asset("SMH", "SEMICONDUCTORS", "SEMIS", "SECTORS", "equity"),
]

# --- Stocks (default watchlist; the user can add their own) -----------------
STOCKS: list[Asset] = [
    Asset("NVDA", "NVIDIA", "NVDA", "STOCKS", "equity"),
    Asset("AAPL", "APPLE", "AAPL", "STOCKS", "equity"),
    Asset("MSFT", "MICROSOFT", "MSFT", "STOCKS", "equity"),
    Asset("AMZN", "AMAZON", "AMZN", "STOCKS", "equity"),
    Asset("GOOGL", "ALPHABET", "GOOGL", "STOCKS", "equity"),
    Asset("META", "META", "META", "STOCKS", "equity"),
    Asset("TSLA", "TESLA", "TSLA", "STOCKS", "equity"),
    Asset("AVGO", "BROADCOM", "AVGO", "STOCKS", "equity"),
    Asset("JPM", "JPMORGAN", "JPM", "STOCKS", "equity"),
    Asset("XOM", "EXXON", "XOM", "STOCKS", "equity"),
    Asset("LLY", "ELI LILLY", "LLY", "STOCKS", "equity"),
    Asset("COIN", "COINBASE", "COIN", "STOCKS", "equity"),
    Asset("MSTR", "STRATEGY", "MSTR", "STOCKS", "equity"),
    Asset("ASML", "ASML", "ASML", "STOCKS", "equity"),
    Asset("TSM", "TSMC", "TSM", "STOCKS", "equity"),
    Asset("PLTR", "PALANTIR", "PLTR", "STOCKS", "equity"),
]

# --- Indices / FX / Rates -----------------------------------------------------
MACRO: list[Asset] = [
    Asset("^GSPC", "S&P 500", "SPX", "INDICES", "index"),
    Asset("^NDX", "NASDAQ 100", "NDX", "INDICES", "index"),
    Asset("^DJI", "DOW JONES", "US30", "INDICES", "index"),
    Asset("^GDAXI", "DAX", "DAX", "INDICES", "index"),
    Asset("^FTSE", "FTSE 100", "FTSE", "INDICES", "index"),
    Asset("^N225", "NIKKEI", "NIKKEI", "INDICES", "index"),
    Asset("^VIX", "VIX", "VIX", "INDICES", "index"),
    Asset("DX-Y.NYB", "DXY", "DXY", "FX", "fx"),
    Asset("EURUSD=X", "EUR/USD", "EURUSD", "FX", "fx"),
    Asset("GBPUSD=X", "GBP/USD", "GBPUSD", "FX", "fx"),
    Asset("USDJPY=X", "USD/JPY", "USDJPY", "FX", "fx"),
    Asset("^TNX", "US 10Y YIELD", "US10Y", "RATES", "bond"),
]

# Command aliases → ticker (for the command bar: "GIP GOLD", "SET OIL")
ALIASES: dict[str, str] = {
    "GOLD": "GC=F", "SILVER": "SI=F", "PLATINUM": "PL=F", "PALLADIUM": "PA=F",
    "OIL": "CL=F", "WTI": "CL=F", "CRUDE": "CL=F", "BRENT": "BZ=F",
    "COPPER": "HG=F", "NATGAS": "NG=F", "GAS": "NG=F",
    "US30": "^DJI", "DOW": "^DJI", "SPX": "^GSPC", "SP500": "^GSPC",
    "NDX": "^NDX", "NASDAQ": "^NDX", "US100": "^NDX", "DAX": "^GDAXI",
    "FTSE": "^FTSE", "NIKKEI": "^N225", "VIX": "^VIX", "DXY": "DX-Y.NYB",
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
    "US10Y": "^TNX", "BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD",
}


def all_assets() -> list[Asset]:
    return COMMODITIES + REGIONS + ASSET_CLASSES + SECTORS + STOCKS + MACRO


def resolve_ticker(text: str) -> str:
    """'gold' → 'GC=F', 'nvda' → 'NVDA', 'btc' → 'BTC-USD'."""
    t = text.strip().upper()
    if t in ALIASES:
        return ALIASES[t]
    for a in all_assets():
        if t in (a.short, a.name, a.ticker):
            return a.ticker
    return t  # unknown → try it as a raw yfinance ticker


# --------------------------------------------------------------------------- #
# yfinance
# --------------------------------------------------------------------------- #
def fetch_history(tickers: Iterable[str], period: str = "6mo",
                  interval: str = "1d") -> pd.DataFrame:
    """
    Returns a MultiIndex DataFrame (ticker, field) with Open/High/Low/Close/Volume.
    On failure → empty DataFrame.
    """
    tickers = sorted(set(t for t in tickers if t))
    if not tickers or yf is None:
        return pd.DataFrame()
    try:
        df = yf.download(tickers, period=period, interval=interval,
                         group_by="ticker", auto_adjust=True, progress=False,
                         threads=True)
        if df is None or df.empty:
            return pd.DataFrame()
        # yfinance returns flat columns when only one ticker is requested
        if len(tickers) == 1 and not isinstance(df.columns, pd.MultiIndex):
            df.columns = pd.MultiIndex.from_product([tickers, df.columns])
        return df
    except Exception:
        return pd.DataFrame()


def closes(df: pd.DataFrame) -> pd.DataFrame:
    """MultiIndex → Close matrix (columns = tickers)."""
    if df.empty:
        return pd.DataFrame()
    out = {}
    for t in df.columns.get_level_values(0).unique():
        try:
            s = df[t]["Close"]
            if s.notna().sum() > 5:
                out[t] = s
        except KeyError:
            continue
    return pd.DataFrame(out).ffill()


def volumes(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    out = {}
    for t in df.columns.get_level_values(0).unique():
        try:
            out[t] = df[t]["Volume"]
        except KeyError:
            continue
    return pd.DataFrame(out).fillna(0)


def fetch_quote_info(ticker: str) -> dict:
    """Basic fundamentals/description for the DES command."""
    if yf is None:
        return {}
    try:
        info = yf.Ticker(ticker).info or {}
        keys = ["longName", "shortName", "sector", "industry", "marketCap",
                "trailingPE", "forwardPE", "dividendYield", "beta",
                "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "longBusinessSummary",
                "currency", "exchange"]
        return {k: info.get(k) for k in keys if info.get(k) is not None}
    except Exception:
        return {}


# --------------------------------------------------------------------------- #
# CoinGecko
# --------------------------------------------------------------------------- #
CG = "https://api.coingecko.com/api/v3"


def fetch_crypto_markets(n: int = 100) -> pd.DataFrame:
    """Top-N crypto by market cap with % changes over 1h/24h/7d/30d."""
    try:
        r = requests.get(f"{CG}/coins/markets", params={
            "vs_currency": "usd", "order": "market_cap_desc", "per_page": n,
            "page": 1, "sparkline": "true",
            "price_change_percentage": "1h,24h,7d,30d"},
            timeout=HTTP_TIMEOUT, headers=UA)
        r.raise_for_status()
        rows = r.json()
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df["spark"] = df["sparkline_in_7d"].apply(
            lambda d: (d or {}).get("price", []) if isinstance(d, dict) else [])
        keep = ["id", "symbol", "name", "current_price", "market_cap",
                "market_cap_rank", "total_volume",
                "price_change_percentage_1h_in_currency",
                "price_change_percentage_24h_in_currency",
                "price_change_percentage_7d_in_currency",
                "price_change_percentage_30d_in_currency", "spark"]
        df = df[[k for k in keep if k in df.columns]].rename(columns={
            "price_change_percentage_1h_in_currency": "chg_1h",
            "price_change_percentage_24h_in_currency": "chg_24h",
            "price_change_percentage_7d_in_currency": "chg_7d",
            "price_change_percentage_30d_in_currency": "chg_30d"})
        df["symbol"] = df["symbol"].str.upper()
        return df
    except Exception:
        return pd.DataFrame()


def fetch_crypto_global() -> dict:
    """Total crypto market cap + BTC dominance (for capital-rotation analysis)."""
    try:
        r = requests.get(f"{CG}/global", timeout=HTTP_TIMEOUT, headers=UA)
        r.raise_for_status()
        d = r.json().get("data", {})
        return {
            "total_mcap_usd": d.get("total_market_cap", {}).get("usd"),
            "mcap_chg_24h": d.get("market_cap_change_percentage_24h_usd"),
            "btc_dominance": d.get("market_cap_percentage", {}).get("btc"),
            "eth_dominance": d.get("market_cap_percentage", {}).get("eth"),
        }
    except Exception:
        return {}


def fetch_crypto_trending() -> list[dict]:
    try:
        r = requests.get(f"{CG}/search/trending", timeout=HTTP_TIMEOUT, headers=UA)
        r.raise_for_status()
        out = []
        for c in r.json().get("coins", []):
            it = c.get("item", {})
            out.append({"name": it.get("name"), "symbol": it.get("symbol"),
                        "rank": it.get("market_cap_rank"),
                        "score": it.get("score")})
        return out
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# DexScreener (meme coins / new on-chain tokens)
# --------------------------------------------------------------------------- #
DEX = "https://api.dexscreener.com"


def _dex_get(path: str):
    r = requests.get(f"{DEX}{path}", timeout=HTTP_TIMEOUT, headers=UA)
    r.raise_for_status()
    return r.json()


def fetch_dex_candidates() -> list[dict]:
    """
    Candidate new tokens: (a) latest token profiles, (b) latest boosted,
    (c) top boosted. Returns a de-duplicated list of {chainId, tokenAddress, ...}.
    """
    seen, out = set(), []
    for path in ("/token-profiles/latest/v1", "/token-boosts/latest/v1",
                 "/token-boosts/top/v1"):
        try:
            for it in _dex_get(path) or []:
                key = (it.get("chainId"), it.get("tokenAddress"))
                if None in key or key in seen:
                    continue
                seen.add(key)
                out.append(it)
        except Exception:
            continue
        time.sleep(0.2)
    return out


def fetch_dex_pairs(chain: str, addresses: list[str]) -> list[dict]:
    """Pair data (price, liquidity, volume, txns, age) for ≤30 tokens per call."""
    out = []
    for i in range(0, len(addresses), 30):
        chunk = ",".join(addresses[i:i + 30])
        try:
            out.extend(_dex_get(f"/tokens/v1/{chain}/{chunk}") or [])
        except Exception:
            continue
        time.sleep(0.25)
    return out


def dex_search(query: str) -> list[dict]:
    try:
        return _dex_get(f"/latest/dex/search?q={query}").get("pairs", []) or []
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# Token security (free)
# --------------------------------------------------------------------------- #
GOPLUS_CHAIN_IDS = {"ethereum": "1", "bsc": "56", "base": "8453",
                    "arbitrum": "42161", "polygon": "137", "avalanche": "43114"}


def token_security(chain: str, address: str) -> dict:
    """
    Returns flags: honeypot / mintable / owner_can_change_tax / buy_tax /
    sell_tax / holder_count. Empty dict if the chain is unsupported.
    """
    try:
        if chain == "solana":
            r = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{address}/report/summary",
                             timeout=HTTP_TIMEOUT, headers=UA)
            if r.ok:
                d = r.json()
                risks = [x.get("name", "") for x in d.get("risks", [])]
                return {"source": "rugcheck", "score": d.get("score"),
                        "risks": risks,
                        "honeypot": any("honeypot" in x.lower() for x in risks),
                        "mintable": any("mint" in x.lower() for x in risks)}
        cid = GOPLUS_CHAIN_IDS.get(chain)
        if cid:
            r = requests.get(f"https://api.gopluslabs.io/api/v1/token_security/{cid}",
                             params={"contract_addresses": address},
                             timeout=HTTP_TIMEOUT, headers=UA)
            if r.ok:
                d = (r.json().get("result") or {}).get(address.lower(), {})
                if d:
                    def f(k):
                        try:
                            return float(d.get(k) or 0)
                        except (TypeError, ValueError):
                            return 0.0
                    return {"source": "goplus",
                            "honeypot": d.get("is_honeypot") == "1",
                            "mintable": d.get("is_mintable") == "1",
                            "owner_can_change_tax": d.get("slippage_modifiable") == "1",
                            "buy_tax": f("buy_tax") * 100,
                            "sell_tax": f("sell_tax") * 100,
                            "holder_count": int(f("holder_count")),
                            "risks": []}
    except Exception:
        pass
    return {}
