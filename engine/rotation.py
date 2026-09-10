"""
engine/rotation.py — Μηχανή "ροής κεφαλαίου" (capital rotation).

Ιδέα: δεν βλέπουμε πραγματικές εισροές/εκροές (δεν υπάρχει δωρεάν API), αλλά
μπορούμε να τις προσεγγίσουμε με τρία σήματα ανά asset:

  1. Relative strength (RS): σταθμισμένα z-scores των αποδόσεων 1d/5d/20d/60d
     σε σχέση με όλο το σύμπαν (cross-sectional). Θετικό = το χρήμα προτιμά
     αυτό το asset σε σχέση με τα άλλα.
  2. Flow proxy: dollar volume 5 ημερών / dollar volume 60 ημερών × πρόσημο
     απόδοσης 5d. Αυξημένος όγκος ΜΕ άνοδο = εισροή, ΜΕ πτώση = εκροή.
  3. Trend: θέση τιμής ως προς SMA20 & SMA50.

Σύνθετο score ∈ [-100, +100]. Το πρόσημο δίνει INFLOW / OUTFLOW, το μέγεθος
την ένταση. Στη συνέχεια ομαδοποιούμε ανά κέντρο αγοράς / κλάδο / κλάση για
να πούμε "το κεφάλαιο φεύγει από Χ και πάει σε Υ".

Upgrade path:
  - Βάλε πραγματικά ETF flows (π.χ. ETF.com CSV) ως 4ο παράγοντα.
  - Αντικατέστησε τα σταθερά βάρη με βάρη που εκτιμώνται από cross-sectional
    regression (Fama-MacBeth) στο ιστορικό — καλό project για το portfolio σου.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

HORIZONS = {"ret_1d": 1, "ret_5d": 5, "ret_20d": 20, "ret_60d": 60}
RS_WEIGHTS = {"ret_1d": 0.10, "ret_5d": 0.30, "ret_20d": 0.35, "ret_60d": 0.25}


def _zscore(s: pd.Series) -> pd.Series:
    sd = s.std(ddof=0)
    if not sd or np.isnan(sd):
        return s * 0
    return (s - s.mean()) / sd


def asset_metrics(close: pd.DataFrame, volume: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Είσοδος: close (index=ημερομηνία, columns=tickers), volume (προαιρετικό).
    Έξοδος: DataFrame ανά ticker με last, ret_*, vol_20d, sma20/50, flow_proxy,
            rs_score, trend_score, flow_score, score, regime.
    """
    if close.empty:
        return pd.DataFrame()
    close = close.dropna(axis=1, thresh=10).ffill()
    rows = {}
    for t in close.columns:
        s = close[t].dropna()
        if len(s) < 6:
            continue
        last = float(s.iloc[-1])
        m = {"last": last}
        for k, n in HORIZONS.items():
            m[k] = float(s.iloc[-1] / s.iloc[-n - 1] - 1) * 100 if len(s) > n else np.nan
        rets = s.pct_change().dropna()
        m["vol_20d"] = float(rets.tail(20).std() * np.sqrt(252) * 100) if len(rets) >= 5 else np.nan
        m["sma20"] = float(s.tail(20).mean())
        m["sma50"] = float(s.tail(50).mean()) if len(s) >= 50 else m["sma20"]
        m["hi_60d"] = float(s.tail(60).max())
        m["lo_60d"] = float(s.tail(60).min())
        # flow proxy
        if volume is not None and t in volume.columns:
            dv = (close[t] * volume[t]).dropna()
            if len(dv) >= 10 and dv.tail(60).mean() > 0:
                ratio = dv.tail(5).mean() / dv.tail(60).mean()
                sign = np.sign(m["ret_5d"]) if not np.isnan(m["ret_5d"]) else 0
                m["flow_proxy"] = float((ratio - 1) * sign * 100)
            else:
                m["flow_proxy"] = 0.0
        else:
            m["flow_proxy"] = 0.0
        rows[t] = m
    df = pd.DataFrame(rows).T
    if df.empty:
        return df

    # 1) relative strength — cross-sectional z-scores
    rs = sum(RS_WEIGHTS[k] * _zscore(df[k].fillna(0)) for k in RS_WEIGHTS)
    df["rs_score"] = rs.clip(-3, 3) / 3 * 100

    # 2) trend
    trend = (np.where(df["last"] > df["sma20"], 1, -1) +
             np.where(df["last"] > df["sma50"], 1, -1) +
             np.where(df["sma20"] > df["sma50"], 1, -1)) / 3
    df["trend_score"] = trend * 100

    # 3) flow
    df["flow_score"] = _zscore(df["flow_proxy"].fillna(0)).clip(-3, 3) / 3 * 100

    df["score"] = (0.5 * df["rs_score"] + 0.3 * df["trend_score"] +
                   0.2 * df["flow_score"]).round(1)
    df["regime"] = np.select(
        [df["score"] >= 25, df["score"] <= -25],
        ["INFLOW", "OUTFLOW"], "NEUTRAL")
    return df.sort_values("score", ascending=False)


def group_rotation(metrics: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    """
    mapping: ticker → όνομα ομάδας (κέντρο/κλάδος/κλάση).
    Επιστρέφει score ανά ομάδα + ταξινόμηση από εισροή σε εκροή.
    """
    if metrics.empty:
        return pd.DataFrame()
    m = metrics.copy()
    m["group"] = m.index.map(mapping)
    g = m.dropna(subset=["group"]).groupby("group").agg(
        score=("score", "mean"), ret_5d=("ret_5d", "mean"),
        ret_20d=("ret_20d", "mean"), n=("score", "size")).round(1)
    g["regime"] = np.select([g["score"] >= 20, g["score"] <= -20],
                            ["INFLOW", "OUTFLOW"], "NEUTRAL")
    return g.sort_values("score", ascending=False)


def rotation_story(g: pd.DataFrame, top: int = 3) -> dict:
    """'Από πού φεύγει και πού πάει το κεφάλαιο' σε δομημένη μορφή."""
    if g.empty:
        return {"to": [], "from": [], "n_in": 0, "n_out": 0, "n": 0}
    return {
        "to": [(i, r.score) for i, r in g.head(top).iterrows()],
        "from": [(i, r.score) for i, r in g.tail(top).iloc[::-1].iterrows()],
        "n_in": int((g.regime == "INFLOW").sum()),
        "n_out": int((g.regime == "OUTFLOW").sum()),
        "n": len(g),
    }


def breadth(metrics: pd.DataFrame) -> dict:
    """Πλάτος αγοράς: % assets πάνω από SMA20/50, % με θετικό 5d."""
    if metrics.empty:
        return {}
    return {
        "pct_above_sma20": round(float((metrics["last"] > metrics["sma20"]).mean() * 100), 1),
        "pct_above_sma50": round(float((metrics["last"] > metrics["sma50"]).mean() * 100), 1),
        "pct_pos_5d": round(float((metrics["ret_5d"] > 0).mean() * 100), 1),
        "n": len(metrics),
    }
