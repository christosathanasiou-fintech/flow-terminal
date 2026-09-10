"""End-to-end: τρέχει κάθε module με mocked δεδομένα (χωρίς internet)."""
import time
import numpy as np, pandas as pd
from streamlit.testing.v1 import AppTest
from engine import data as D

def _hist(tickers, period="6mo", interval="1d"):
    n = 130 if interval == "1d" else 60
    idx = pd.bdate_range("2026-03-01", periods=n); rng = np.random.default_rng(abs(hash(tuple(tickers))) % 2**32)
    f = {}
    for t in sorted(set(tickers)):
        c = 100 * np.cumprod(1 + rng.normal(0.0005, 0.012, n))
        f[t] = pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * .99, "Close": c,
                             "Volume": rng.integers(1e5, 1e6, n)}, index=idx)
    return pd.concat(f, axis=1)

def _crypto(n=100):
    rng = np.random.default_rng(3)
    return pd.DataFrame({"id": [f"c{i}" for i in range(n)], "symbol": ["BTC", "ETH", "USDT"] + [f"A{i}" for i in range(n - 3)],
                         "name": [f"Coin {i}" for i in range(n)], "current_price": rng.uniform(0.01, 60000, n),
                         "market_cap": rng.uniform(1e8, 1e12, n), "market_cap_rank": range(1, n + 1),
                         "total_volume": rng.uniform(1e6, 1e10, n), "chg_1h": rng.normal(0, 1, n),
                         "chg_24h": rng.normal(0, 4, n), "chg_7d": rng.normal(0, 8, n), "chg_30d": rng.normal(0, 15, n),
                         "spark": [list(np.cumsum(rng.normal(0, 1, 60)) + 100) for _ in range(n)]})

def _pair(i):
    return {"baseToken": {"symbol": f"MEME{i}", "name": f"Meme {i}", "address": f"0x{i:040x}"}, "chainId": "base",
            "dexId": "uniswap", "url": "https://dexscreener.com/base/x", "priceUsd": "0.0012",
            "liquidity": {"usd": 50000 + i * 40000}, "volume": {"h24": 200000, "h1": 15000},
            "txns": {"h1": {"buys": 100, "sells": 60}, "h24": {"buys": 800, "sells": 500}},
            "priceChange": {"m5": 1, "h1": 5, "h6": 20, "h24": 40}, "pairCreatedAt": (time.time() - 3600 * 20) * 1000,
            "info": {"websites": [{}], "socials": [{}, {}]}, "boosts": {"active": 5}, "fdv": 800000}

def _patch(monkeypatch):
    monkeypatch.setattr(D, "fetch_history", _hist)
    monkeypatch.setattr(D, "fetch_crypto_markets", lambda n=100: _crypto(n))
    monkeypatch.setattr(D, "fetch_crypto_global", lambda: {"total_mcap_usd": 3.1e12, "mcap_chg_24h": 1.2, "btc_dominance": 55.0, "eth_dominance": 12.0})
    monkeypatch.setattr(D, "fetch_crypto_trending", lambda: [{"name": "X", "symbol": "X", "rank": 50, "score": 0}])
    monkeypatch.setattr(D, "fetch_dex_candidates", lambda: [{"chainId": "base", "tokenAddress": f"0x{i:040x}"} for i in range(6)])
    monkeypatch.setattr(D, "fetch_dex_pairs", lambda ch, addrs: [_pair(i) for i in range(len(addrs))])
    monkeypatch.setattr(D, "dex_search", lambda q: [_pair(9)])
    monkeypatch.setattr(D, "token_security", lambda ch, a: {"source": "goplus", "honeypot": False})
    monkeypatch.setattr(D, "fetch_quote_info", lambda t: {"marketCap": 3e12, "trailingPE": 30.0, "longBusinessSummary": "test"})

import pytest
@pytest.mark.parametrize("mod", ["BRIEF", "GLOBE", "CHART", "SETUPS", "STOCKS", "COMM", "CRYPTO", "RADAR", "FX", "ASK"])
def test_module_renders(monkeypatch, mod):
    _patch(monkeypatch)
    at = AppTest.from_file("../app.py", default_timeout=120)
    at.session_state["module"] = mod
    if mod == "CHART":
        at.session_state["cmd_target"] = ("DES", "NVDA")
    if mod == "RADAR":
        at.session_state["cmd_target"] = ("MEME", "WIF")
    at.run()
    assert not at.exception, [e.value for e in at.exception]
