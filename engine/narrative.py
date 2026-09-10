"""
engine/narrative.py — "ΜΕ ΑΠΛΑ ΛΟΓΙΑ": μετατροπή αριθμών σε κείμενο.

Δύο επίπεδα:
  1. Rule-based (πάντα διαθέσιμο, δωρεάν): συνθέτει προτάσεις από τα metrics.
  2. LLM (προαιρετικό): αν υπάρχει ANTHROPIC_API_KEY στο περιβάλλον ή στα
     Streamlit secrets, η εντολή ASK στέλνει το snapshot της αγοράς στο Claude
     και επιστρέφει απάντηση. Χωρίς κλειδί, το ASK απαντά με το rule-based.

Upgrade path:
  - Δώσε στο LLM tools (function calling) ώστε να ζητά το ίδιο ιστορικό
    για συγκεκριμένο ticker αντί να παίρνει μόνο το snapshot.
"""
from __future__ import annotations

import json
import os

import pandas as pd

DISCLAIMER = ("Ενημερωτικοί σκοποί μόνο. Δεν αποτελεί επενδυτική συμβουλή. "
              "Η τελική απόφαση είναι αποκλειστικά δική σου.")


def fmt_pct(x) -> str:
    try:
        return f"{float(x):+.2f}%"
    except (TypeError, ValueError):
        return "n/a"


def rotation_text(story: dict, breadth: dict, label: str = "κέντρα") -> str:
    if not story or not story.get("to"):
        return "Δεν υπάρχουν αρκετά δεδομένα για την ανάλυση ροής."
    to = ", ".join(f"{n} ({s:+.0f})" for n, s in story["to"])
    frm = ", ".join(f"{n} ({s:+.0f})" for n, s in story["from"])
    parts = [
        f"Το κεφάλαιο ΠΑΕΙ προς: {to}.",
        f"Το κεφάλαιο ΦΕΥΓΕΙ από: {frm}.",
        f"{story['n_in']}/{story['n']} {label} σε εισροή, {story['n_out']}/{story['n']} σε εκροή.",
    ]
    if breadth:
        b = breadth
        mood = ("ευρεία ανοδική συμμετοχή" if b["pct_above_sma50"] >= 65 else
                "ευρεία αδυναμία" if b["pct_above_sma50"] <= 35 else "επιλεκτική αγορά")
        parts.append(f"Πλάτος: {b['pct_above_sma50']:.0f}% πάνω από SMA50, "
                     f"{b['pct_pos_5d']:.0f}% θετικά στο 5ήμερο → {mood}.")
    return " ".join(parts)


def asset_text(ticker: str, name: str, m: pd.Series, setup=None) -> str:
    """Μία παράγραφος για ένα asset (εντολή DES / VER)."""
    s = (f"{name} ({ticker}) στα {m['last']:,.2f}: {fmt_pct(m['ret_1d'])} σήμερα, "
         f"{fmt_pct(m['ret_5d'])} 5ήμερο, {fmt_pct(m['ret_20d'])} μήνα, "
         f"{fmt_pct(m['ret_60d'])} τρίμηνο. Μεταβλητότητα {m['vol_20d']:.0f}% ετησ. ")
    s += (f"Rotation score {m['score']:+.0f} → {m['regime']}. ")
    if setup is not None:
        s += (f"Setup: {setup.direction} με conviction {setup.conviction}/100, "
              f"τάση {setup.trend}, RSI {setup.rsi:.0f}. "
              f"Είσοδος ~{setup.entry:,.2f}, stop {setup.stop:,.2f}, "
              f"target {setup.target:,.2f} (R:R {setup.rr}). "
              f"Γιατί: {'; '.join(setup.rationale)}.")
    return s


def commodities_text(m: pd.DataFrame, names: dict[str, str]) -> str:
    if m.empty:
        return "Χωρίς δεδομένα εμπορευμάτων."
    up = m[m["ret_1d"] > 0]; dn = m[m["ret_1d"] <= 0]
    best = m["ret_5d"].idxmax(); worst = m["ret_5d"].idxmin()
    return (f"Στα {len(m)} εμπορεύματα, {len(up)} ανεβαίνουν και {len(dn)} πέφτουν σήμερα. "
            f"Ισχυρότερο 5ημέρου: {names.get(best, best)} {fmt_pct(m.loc[best, 'ret_5d'])}. "
            f"Αδύναμο: {names.get(worst, worst)} {fmt_pct(m.loc[worst, 'ret_5d'])}. "
            f"Εισροή: {', '.join(names.get(t, t) for t in m[m.regime == 'INFLOW'].index[:4]) or '—'}. "
            f"Εκροή: {', '.join(names.get(t, t) for t in m[m.regime == 'OUTFLOW'].index[:4]) or '—'}.")


def crypto_text(cg: pd.DataFrame, glob: dict) -> str:
    if cg.empty:
        return "Χωρίς δεδομένα crypto (CoinGecko rate limit; ξαναδοκίμασε σε 1')."
    top = cg.head(20)
    s = ""
    if glob.get("total_mcap_usd"):
        s += (f"Συνολική κεφαλαιοποίηση ${glob['total_mcap_usd']/1e12:.2f}T "
              f"({fmt_pct(glob.get('mcap_chg_24h'))} 24h), BTC dominance "
              f"{glob.get('btc_dominance', 0):.1f}%. ")
    btc = cg[cg.symbol == "BTC"]
    alts = top[~top.symbol.isin(["BTC", "USDT", "USDC"])]
    if not btc.empty and not alts.empty:
        d = float(alts.chg_7d.mean() - btc.chg_7d.iloc[0])
        s += (f"Alts 7d vs BTC: {d:+.1f} μον. → "
              f"{'κεφάλαιο ρέει προς alts' if d > 2 else 'BTC κρατά το κεφάλαιο' if d < -2 else 'ισορροπία'}. ")
    w = top.loc[top.chg_24h.idxmax()]; l = top.loc[top.chg_24h.idxmin()]
    s += f"Top-20 24h: καλύτερο {w.symbol} {fmt_pct(w.chg_24h)}, χειρότερο {l.symbol} {fmt_pct(l.chg_24h)}."
    return s


def meme_text(df: pd.DataFrame) -> str:
    if df.empty:
        return "Το radar δεν βρήκε tokens που περνούν τα φίλτρα αυτή τη στιγμή."
    a = df[df.grade == "A"]; b = df[df.grade == "B"]
    s = (f"Σαρώθηκαν {len(df)} νέα tokens: {len(a)} grade A, {len(b)} grade B. ")
    if not a.empty:
        s += "Ξεχωρίζουν: " + ", ".join(
            f"{r.symbol} ({r.chain}, score {r.score}, liq ${r.liq/1e3:.0f}k, {r.age_h or 0:.0f}h)"
            for r in a.head(3).itertuples()) + ". "
    s += ("Υπενθύμιση: το score μετρά δραστηριότητα και red flags, όχι μελλοντική απόδοση· "
          "τα περισσότερα meme coins πάνε στο μηδέν.")
    return s


# --------------------------------------------------------------------------- #
# LLM (προαιρετικό)
# --------------------------------------------------------------------------- #
def _api_key() -> str | None:
    k = os.environ.get("ANTHROPIC_API_KEY")
    if k:
        return k
    try:
        import streamlit as st
        return st.secrets.get("ANTHROPIC_API_KEY")  # type: ignore[attr-defined]
    except Exception:
        return None


def ask_llm(question: str, snapshot: dict) -> str:
    """Στέλνει ερώτηση + snapshot αγοράς στο Claude. Fallback χωρίς κλειδί."""
    key = _api_key()
    if not key:
        return ("Δεν έχει οριστεί ANTHROPIC_API_KEY, οπότε απαντώ μόνο με τους κανόνες "
                "του terminal. Βάλε το κλειδί στο .streamlit/secrets.toml για πλήρες ASK.")
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        model = os.environ.get("FLOW_LLM_MODEL", "claude-sonnet-4-6")
        sys = ("Είσαι ο αναλυτής του FLOW TERMINAL. Απαντάς στα ελληνικά, σύντομα, με "
               "συγκεκριμένα επίπεδα και αριθμούς από το snapshot. Κρατάς τους τεχνικούς "
               "όρους (RSI, ATR, drawdown) στα αγγλικά. Ξεκαθαρίζεις τι είναι γεγονός, τι "
               "εκτίμηση. Δεν δίνεις εξατομικευμένη επενδυτική συμβουλή· περιγράφεις σενάρια.")
        msg = client.messages.create(
            model=model, max_tokens=800, system=sys,
            messages=[{"role": "user", "content":
                       f"SNAPSHOT (JSON):\n{json.dumps(snapshot, ensure_ascii=False, default=str)[:12000]}"
                       f"\n\nΕΡΩΤΗΣΗ: {question}"}])
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    except Exception as e:  # noqa: BLE001
        return f"Σφάλμα LLM: {e}"
