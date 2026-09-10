"""Offline tests με συνθετικά δεδομένα — τρέξε: python -m pytest tests"""
import numpy as np, pandas as pd
from engine import rotation as R, signals as S, meme as M, data as D

def _hist():
    idx = pd.bdate_range("2026-01-01", periods=120); rng = np.random.default_rng(0); f = {}
    for t in ["GC=F", "SPY"]:
        c = 100 * np.cumprod(1 + rng.normal(0, 0.01, len(idx)))
        f[t] = pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * .99, "Close": c,
                             "Volume": rng.integers(1e5, 1e6, len(idx))}, index=idx)
    return pd.concat(f, axis=1)

def test_metrics_and_setups():
    h = _hist(); m = R.asset_metrics(D.closes(h), D.volumes(h))
    assert set(m.index) == {"GC=F", "SPY"} and m["score"].between(-100, 100).all()
    s = S.build_setups(h, ["GC=F", "SPY"], m)
    assert len(s) == 2 and all(x.direction in ("LONG", "SHORT", "WAIT") for x in s)

def test_meme_honeypot_rejected():
    pair = {"baseToken": {"symbol": "X", "address": "0x1"}, "liquidity": {"usd": 1e6}, "volume": {"h24": 1e6},
            "txns": {"h24": {"buys": 500, "sells": 500}}, "priceChange": {}}
    assert M.score_pair(pair, {"honeypot": True})["score"] == 0
