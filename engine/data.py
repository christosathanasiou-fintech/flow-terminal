"""
engine/data.py — Πηγές δεδομένων του FLOW TERMINAL.

Όλες οι συναρτήσεις είναι "ασφαλείς": σε αποτυχία δικτύου επιστρέφουν κενά
DataFrames/lists αντί να ρίχνουν exception, ώστε το UI να μην πέφτει ποτέ.

Πηγές (όλες δωρεάν, χωρίς API key):
  • yfinance      → μετοχές, δείκτες, ETFs, futures εμπορευμάτων, FX, ομόλογα
                    (US equities ~15' καθυστέρηση, futures/FX σχεδόν real-time)
  • CoinGecko     → top-100 crypto, trending (real-time, rate limit ~30 req/min)
  • DexScreener   → νέα tokens, boosted tokens, on-chain pair data (real-time)
  • GoPlus        → token security για EVM chains (honeypot, mintable, tax)
  • RugCheck      → token security για Solana

Upgrade path:
  - Για πραγματικό real-time στις US μετοχές: αντικατέστησε fetch_history με
    Polygon.io / Alpaca websocket (δωρεάν tier υπάρχει και στα δύο).
  - Για ETF flows (πραγματικές εισροές/εκροές αντί proxy): ETF.com ή
    Bloomberg — δεν υπάρχει δωρεάν API, γι' αυτό εδώ χρησιμοποιούμε proxy
    (dollar volume × κατεύθυνση).
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
# ΣΥΜΠΑΝ ΑΓΟΡΩΝ (universe)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Asset:
    ticker: str          # yfinance symbol
    name: str            # ελληνικό όνομα για την οθόνη
    short: str           # σύντομο label (GOLD, WTI, ...)
    group: str           # ομάδα: ΜΕΤΑΛΛΑ / ΕΝΕΡΓΕΙΑ / ΑΓΡΟΤΙΚΑ / ΔΕΙΚΤΕΣ / ...
    asset_class: str     # commodity / equity / index / fx / bond
    region: str = ""     # για την υδρόγειο (κέντρο αγοράς)
    lat: float = 0.0
    lon: float = 0.0


# --- Εμπορεύματα (futures συνεχούς συμβολαίου στο yfinance) -----------------
COMMODITIES: list[Asset] = [
    Asset("GC=F", "ΧΡΥΣΟΣ", "GOLD", "ΜΕΤΑΛΛΑ", "commodity"),
    Asset("SI=F", "ΑΣΗΜΙ", "SILVER", "ΜΕΤΑΛΛΑ", "commodity"),
    Asset("HG=F", "ΧΑΛΚΟΣ", "COPPER", "ΜΕΤΑΛΛΑ", "commodity"),
    Asset("PL=F", "ΠΛΑΤΙΝΑ", "PLATINUM", "ΜΕΤΑΛΛΑ", "commodity"),
    Asset("PA=F", "ΠΑΛΛΑΔΙΟ", "PALLADIUM", "ΜΕΤΑΛΛΑ", "commodity"),
    Asset("CL=F", "WTI OIL", "WTI", "ΕΝΕΡΓΕΙΑ", "commodity"),
    Asset("BZ=F", "BRENT", "BRENT", "ΕΝΕΡΓΕΙΑ", "commodity"),
    Asset("NG=F", "NAT GAS", "NATGAS", "ΕΝΕΡΓΕΙΑ", "commodity"),
    Asset("RB=F", "GASOLINE", "RBOB", "ΕΝΕΡΓΕΙΑ", "commodity"),
    Asset("HO=F", "HEATING OIL", "HEATOIL", "ΕΝΕΡΓΕΙΑ", "commodity"),
    Asset("ZW=F", "ΣΙΤΑΡΙ", "WHEAT", "ΑΓΡΟΤΙΚΑ", "commodity"),
    Asset("ZC=F", "ΚΑΛΑΜΠΟΚΙ", "CORN", "ΑΓΡΟΤΙΚΑ", "commodity"),
    Asset("ZS=F", "ΣΟΓΙΑ", "SOYBEANS", "ΑΓΡΟΤΙΚΑ", "commodity"),
    Asset("KC=F", "ΚΑΦΕΣ", "COFFEE", "ΑΓΡΟΤΙΚΑ", "commodity"),
    Asset("SB=F", "ΖΑΧΑΡΗ", "SUGAR", "ΑΓΡΟΤΙΚΑ", "commodity"),
    Asset("CC=F", "ΚΑΚΑΟ", "COCOA", "ΑΓΡΟΤΙΚΑ", "commodity"),
    Asset("CT=F", "ΒΑΜΒΑΚΙ", "COTTON", "ΑΓΡΟΤΙΚΑ", "commodity"),
    Asset("OJ=F", "ΧΥΜΟΣ ΠΟΡΤΟΚΑΛΙ", "OJ", "ΑΓΡΟΤΙΚΑ", "commodity"),
    Asset("LE=F", "LIVE CATTLE", "CATTLE", "ΑΓΡΟΤΙΚΑ", "commodity"),
    Asset("HE=F", "LEAN HOGS", "HOGS", "ΑΓΡΟΤΙΚΑ", "commodity"),
]

# --- Κέντρα αγοράς για την υδρόγειο (ETF ως proxy της κάθε αγοράς) ---------
REGIONS: list[Asset] = [
    Asset("SPY", "ΝΕΑ ΥΟΡΚΗ", "NY", "ΚΕΝΤΡΑ", "index", "New York", 40.71, -74.01),
    Asset("EWU", "ΛΟΝΔΙΝΟ", "LONDON", "ΚΕΝΤΡΑ", "index", "London", 51.51, -0.13),
    Asset("EWG", "ΦΡΑΝΚΦΟΥΡΤΗ", "DAX", "ΚΕΝΤΡΑ", "index", "Frankfurt", 50.11, 8.68),
    Asset("EWQ", "ΠΑΡΙΣΙ", "PARIS", "ΚΕΝΤΡΑ", "index", "Paris", 48.86, 2.35),
    Asset("EWJ", "ΤΟΚΙΟ", "TOKYO", "ΚΕΝΤΡΑ", "index", "Tokyo", 35.68, 139.69),
    Asset("MCHI", "ΣΑΓΚΑΗ", "SHANGHAI", "ΚΕΝΤΡΑ", "index", "Shanghai", 31.23, 121.47),
    Asset("EWH", "ΧΟΝΓΚ ΚΟΝΓΚ", "HK", "ΚΕΝΤΡΑ", "index", "Hong Kong", 22.32, 114.17),
    Asset("INDA", "ΜΟΥΜΠΑΙ", "MUMBAI", "ΚΕΝΤΡΑ", "index", "Mumbai", 19.08, 72.88),
    Asset("EWY", "ΣΕΟΥΛ", "SEOUL", "ΚΕΝΤΡΑ", "index", "Seoul", 37.57, 126.98),
    Asset("EWT", "ΤΑΪΠΕΪ", "TAIPEI", "ΚΕΝΤΡΑ", "index", "Taipei", 25.03, 121.57),
    Asset("EWA", "ΣΙΔΝΕΪ", "SYDNEY", "ΚΕΝΤΡΑ", "index", "Sydney", -33.87, 151.21),
    Asset("EWZ", "ΣΑΟ ΠΑΟΛΟ", "SAOPAULO", "ΚΕΝΤΡΑ", "index", "Sao Paulo", -23.55, -46.63),
    Asset("EWC", "ΤΟΡΟΝΤΟ", "TORONTO", "ΚΕΝΤΡΑ", "index", "Toronto", 43.65, -79.38),
    Asset("EWW", "ΜΕΞΙΚΟ", "MEXICO", "ΚΕΝΤΡΑ", "index", "Mexico City", 19.43, -99.13),
    Asset("KSA", "ΡΙΑΝΤ", "RIYADH", "ΚΕΝΤΡΑ", "index", "Riyadh", 24.71, 46.68),
    Asset("UAE", "ΝΤΟΥΜΠΑΙ", "DUBAI", "ΚΕΝΤΡΑ", "index", "Dubai", 25.20, 55.27),
    Asset("EZA", "ΓΙΟΧΑΝΕΣΜΠΟΥΡΓΚ", "JOBURG", "ΚΕΝΤΡΑ", "index", "Johannesburg", -26.20, 28.04),
    Asset("GREK", "ΑΘΗΝΑ", "ATHENS", "ΚΕΝΤΡΑ", "index", "Athens", 37.98, 23.73),
]

# --- Κλάσεις ενεργητικού για τη ροή κεφαλαίου -------------------------------
ASSET_CLASSES: list[Asset] = [
    Asset("SPY", "US ΜΕΤΟΧΕΣ", "US EQ", "ΚΛΑΣΕΙΣ", "equity"),
    Asset("QQQ", "ΤΕΧΝΟΛΟΓΙΑ", "TECH", "ΚΛΑΣΕΙΣ", "equity"),
    Asset("IWM", "SMALL CAPS", "SMALL", "ΚΛΑΣΕΙΣ", "equity"),
    Asset("EFA", "ΑΝΕΠΤΥΓΜΕΝΕΣ ex-US", "DM", "ΚΛΑΣΕΙΣ", "equity"),
    Asset("EEM", "ΑΝΑΔΥΟΜΕΝΕΣ", "EM", "ΚΛΑΣΕΙΣ", "equity"),
    Asset("TLT", "ΟΜΟΛΟΓΑ 20Y", "BONDS", "ΚΛΑΣΕΙΣ", "bond"),
    Asset("GLD", "ΧΡΥΣΟΣ (ETF)", "GOLD", "ΚΛΑΣΕΙΣ", "commodity"),
    Asset("USO", "ΠΕΤΡΕΛΑΙΟ (ETF)", "OIL", "ΚΛΑΣΕΙΣ", "commodity"),
    Asset("DBA", "ΑΓΡΟΤΙΚΑ (ETF)", "AGRI", "ΚΛΑΣΕΙΣ", "commodity"),
    Asset("UUP", "ΔΟΛΑΡΙΟ", "USD", "ΚΛΑΣΕΙΣ", "fx"),
    Asset("BITO", "CRYPTO (ETF)", "CRYPTO", "ΚΛΑΣΕΙΣ", "crypto"),
]

# --- Κλάδοι S&P 500 -----------------------------------------------------------
SECTORS: list[Asset] = [
    Asset("XLK", "ΤΕΧΝΟΛΟΓΙΑ", "TECH", "ΚΛΑΔΟΙ", "equity"),
    Asset("XLF", "ΧΡΗΜΑΤΟΟΙΚΟΝΟΜΙΚΑ", "FIN", "ΚΛΑΔΟΙ", "equity"),
    Asset("XLE", "ΕΝΕΡΓΕΙΑ", "ENERGY", "ΚΛΑΔΟΙ", "equity"),
    Asset("XLV", "ΥΓΕΙΑ", "HEALTH", "ΚΛΑΔΟΙ", "equity"),
    Asset("XLY", "ΚΑΤΑΝΑΛΩΣΗ ΔΙΑΚΡ.", "DISCR", "ΚΛΑΔΟΙ", "equity"),
    Asset("XLP", "ΚΑΤΑΝΑΛΩΣΗ ΒΑΣ.", "STAPLES", "ΚΛΑΔΟΙ", "equity"),
    Asset("XLI", "ΒΙΟΜΗΧΑΝΙΑ", "INDU", "ΚΛΑΔΟΙ", "equity"),
    Asset("XLU", "ΚΟΙΝΗ ΩΦΕΛΕΙΑ", "UTIL", "ΚΛΑΔΟΙ", "equity"),
    Asset("XLB", "ΥΛΙΚΑ", "MATER", "ΚΛΑΔΟΙ", "equity"),
    Asset("XLRE", "ΑΚΙΝΗΤΑ", "REIT", "ΚΛΑΔΟΙ", "equity"),
    Asset("XLC", "ΕΠΙΚΟΙΝΩΝΙΕΣ", "COMM", "ΚΛΑΔΟΙ", "equity"),
    Asset("SMH", "ΗΜΙΑΓΩΓΟΙ", "SEMIS", "ΚΛΑΔΟΙ", "equity"),
]

# --- Μετοχές (προεπιλεγμένη watchlist, ο χρήστης προσθέτει δικές του) --------
STOCKS: list[Asset] = [
    Asset("NVDA", "NVIDIA", "NVDA", "ΜΕΤΟΧΕΣ", "equity"),
    Asset("AAPL", "APPLE", "AAPL", "ΜΕΤΟΧΕΣ", "equity"),
    Asset("MSFT", "MICROSOFT", "MSFT", "ΜΕΤΟΧΕΣ", "equity"),
    Asset("AMZN", "AMAZON", "AMZN", "ΜΕΤΟΧΕΣ", "equity"),
    Asset("GOOGL", "ALPHABET", "GOOGL", "ΜΕΤΟΧΕΣ", "equity"),
    Asset("META", "META", "META", "ΜΕΤΟΧΕΣ", "equity"),
    Asset("TSLA", "TESLA", "TSLA", "ΜΕΤΟΧΕΣ", "equity"),
    Asset("AVGO", "BROADCOM", "AVGO", "ΜΕΤΟΧΕΣ", "equity"),
    Asset("JPM", "JPMORGAN", "JPM", "ΜΕΤΟΧΕΣ", "equity"),
    Asset("XOM", "EXXON", "XOM", "ΜΕΤΟΧΕΣ", "equity"),
    Asset("LLY", "ELI LILLY", "LLY", "ΜΕΤΟΧΕΣ", "equity"),
    Asset("COIN", "COINBASE", "COIN", "ΜΕΤΟΧΕΣ", "equity"),
    Asset("MSTR", "STRATEGY", "MSTR", "ΜΕΤΟΧΕΣ", "equity"),
    Asset("ASML", "ASML", "ASML", "ΜΕΤΟΧΕΣ", "equity"),
    Asset("TSM", "TSMC", "TSM", "ΜΕΤΟΧΕΣ", "equity"),
    Asset("PLTR", "PALANTIR", "PLTR", "ΜΕΤΟΧΕΣ", "equity"),
]

# --- Δείκτες / FX / Επιτόκια ---------------------------------------------------
MACRO: list[Asset] = [
    Asset("^GSPC", "S&P 500", "SPX", "ΔΕΙΚΤΕΣ", "index"),
    Asset("^NDX", "NASDAQ 100", "NDX", "ΔΕΙΚΤΕΣ", "index"),
    Asset("^DJI", "DOW JONES", "US30", "ΔΕΙΚΤΕΣ", "index"),
    Asset("^GDAXI", "DAX", "DAX", "ΔΕΙΚΤΕΣ", "index"),
    Asset("^FTSE", "FTSE 100", "FTSE", "ΔΕΙΚΤΕΣ", "index"),
    Asset("^N225", "NIKKEI", "NIKKEI", "ΔΕΙΚΤΕΣ", "index"),
    Asset("^VIX", "VIX", "VIX", "ΔΕΙΚΤΕΣ", "index"),
    Asset("DX-Y.NYB", "DXY", "DXY", "FX", "fx"),
    Asset("EURUSD=X", "EUR/USD", "EURUSD", "FX", "fx"),
    Asset("GBPUSD=X", "GBP/USD", "GBPUSD", "FX", "fx"),
    Asset("USDJPY=X", "USD/JPY", "USDJPY", "FX", "fx"),
    Asset("^TNX", "US 10Y YIELD", "US10Y", "ΕΠΙΤΟΚΙΑ", "bond"),
]

# Αντιστοίχιση εντολών → ticker (για το command bar: "GIP GOLD", "SET OIL")
ALIASES: dict[str, str] = {
    "GOLD": "GC=F", "ΧΡΥΣΟΣ": "GC=F", "SILVER": "SI=F", "ΑΣΗΜΙ": "SI=F",
    "OIL": "CL=F", "WTI": "CL=F", "ΠΕΤΡΕΛΑΙΟ": "CL=F", "BRENT": "BZ=F",
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
    return t  # άγνωστο → δοκιμάζουμε ως raw yfinance ticker


# --------------------------------------------------------------------------- #
# yfinance
# --------------------------------------------------------------------------- #
def fetch_history(tickers: Iterable[str], period: str = "6mo",
                  interval: str = "1d") -> pd.DataFrame:
    """
    Επιστρέφει MultiIndex DataFrame (ticker, field) με Open/High/Low/Close/Volume.
    Σε αποτυχία → κενό DataFrame.
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
        # yfinance επιστρέφει flat columns αν ζητηθεί 1 μόνο ticker
        if len(tickers) == 1 and not isinstance(df.columns, pd.MultiIndex):
            df.columns = pd.MultiIndex.from_product([tickers, df.columns])
        return df
    except Exception:
        return pd.DataFrame()


def closes(df: pd.DataFrame) -> pd.DataFrame:
    """MultiIndex → πίνακας Close (στήλες = tickers)."""
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
    """Βασικά fundamentals/περιγραφή για την εντολή DES."""
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
    """Top-N crypto κατά κεφαλαιοποίηση με % μεταβολές 1h/24h/7d/30d."""
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
    """Συνολική κεφαλαιοποίηση crypto + BTC dominance (για τη ροή κεφαλαίου)."""
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
# DexScreener (meme coins / νέα tokens on-chain)
# --------------------------------------------------------------------------- #
DEX = "https://api.dexscreener.com"


def _dex_get(path: str):
    r = requests.get(f"{DEX}{path}", timeout=HTTP_TIMEOUT, headers=UA)
    r.raise_for_status()
    return r.json()


def fetch_dex_candidates() -> list[dict]:
    """
    Υποψήφια νέα tokens: (α) πρόσφατα token profiles, (β) πρόσφατα boosted,
    (γ) top boosted. Επιστρέφει λίστα {chainId, tokenAddress, ...} χωρίς διπλά.
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
    """Δεδομένα pair (τιμή, ρευστότητα, όγκος, txns, ηλικία) για ≤30 tokens."""
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
# Token security (δωρεάν)
# --------------------------------------------------------------------------- #
GOPLUS_CHAIN_IDS = {"ethereum": "1", "bsc": "56", "base": "8453",
                    "arbitrum": "42161", "polygon": "137", "avalanche": "43114"}


def token_security(chain: str, address: str) -> dict:
    """
    Επιστρέφει flags: honeypot / mintable / owner_can_change_tax / buy_tax /
    sell_tax / lp_locked_pct / top10_pct. Κενό dict αν δεν υποστηρίζεται.
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
