"""
engine/narrative.py — "IN PLAIN WORDS": turns numbers into readable text.

Two layers:
  1. Rule-based (always available, free): composes sentences from the metrics.
  2. LLM (optional): if ANTHROPIC_API_KEY is set in the environment or in
     Streamlit secrets, the ASK command sends the market snapshot to Claude
     and returns its answer. Without a key, ASK falls back to the rule-based text.

Upgrade path:
  - Give the LLM tools (function calling) so it can request the history of a
    specific ticker itself instead of only receiving the snapshot.
"""
from __future__ import annotations

import json
import os

import pandas as pd

DISCLAIMER = ("For informational purposes only. Not investment advice. "
              "The final decision is entirely yours.")


def fmt_pct(x) -> str:
    try:
        return f"{float(x):+.2f}%"
    except (TypeError, ValueError):
        return "n/a"


def rotation_text(story: dict, breadth: dict, label: str = "centres") -> str:
    """Summary of where capital is flowing, plus a breadth read."""
    if not story or not story.get("to"):
        return "Not enough data for the flow analysis."
    to = ", ".join(f"{n} ({s:+.0f})" for n, s in story["to"])
    frm = ", ".join(f"{n} ({s:+.0f})" for n, s in story["from"])
    parts = [
        f"Capital is MOVING INTO: {to}.",
        f"Capital is LEAVING: {frm}.",
        f"{story['n_in']}/{story['n']} {label} in inflow, {story['n_out']}/{story['n']} in outflow.",
    ]
    if breadth:
        b = breadth
        mood = ("broad participation to the upside" if b["pct_above_sma50"] >= 65 else
                "broad weakness" if b["pct_above_sma50"] <= 35 else "selective market")
        parts.append(f"Breadth: {b['pct_above_sma50']:.0f}% above SMA50, "
                     f"{b['pct_pos_5d']:.0f}% positive over 5 days → {mood}.")
    return " ".join(parts)


def asset_text(ticker: str, name: str, m: pd.Series, setup=None) -> str:
    """One paragraph for a single asset (DES / VER commands)."""
    s = (f"{name} ({ticker}) at {m['last']:,.2f}: {fmt_pct(m['ret_1d'])} today, "
         f"{fmt_pct(m['ret_5d'])} over 5 days, {fmt_pct(m['ret_20d'])} over a month, "
         f"{fmt_pct(m['ret_60d'])} over 3 months. Volatility {m['vol_20d']:.0f}% annualised. ")
    s += f"Rotation score {m['score']:+.0f} → {m['regime']}. "
    if setup is not None:
        s += (f"Setup: {setup.direction} with conviction {setup.conviction}/100, "
              f"trend {setup.trend}, RSI {setup.rsi:.0f}. "
              f"Entry ~{setup.entry:,.2f}, stop {setup.stop:,.2f}, "
              f"target {setup.target:,.2f} (R:R {setup.rr}). "
              f"Why: {'; '.join(setup.rationale)}.")
    return s


def commodities_text(m: pd.DataFrame, names: dict[str, str]) -> str:
    if m.empty:
        return "No commodity data."
    up = m[m["ret_1d"] > 0]
    dn = m[m["ret_1d"] <= 0]
    best = m["ret_5d"].idxmax()
    worst = m["ret_5d"].idxmin()
    return (f"Of {len(m)} commodities, {len(up)} are up and {len(dn)} are down today. "
            f"Strongest over 5 days: {names.get(best, best)} {fmt_pct(m.loc[best, 'ret_5d'])}. "
            f"Weakest: {names.get(worst, worst)} {fmt_pct(m.loc[worst, 'ret_5d'])}. "
            f"Inflow: {', '.join(names.get(t, t) for t in m[m.regime == 'INFLOW'].index[:4]) or '—'}. "
            f"Outflow: {', '.join(names.get(t, t) for t in m[m.regime == 'OUTFLOW'].index[:4]) or '—'}.")


def crypto_text(cg: pd.DataFrame, glob: dict) -> str:
    if cg.empty:
        return "No crypto data (CoinGecko rate limit; try again in 1 minute)."
    top = cg.head(20)
    s = ""
    if glob.get("total_mcap_usd"):
        s += (f"Total market cap ${glob['total_mcap_usd']/1e12:.2f}T "
              f"({fmt_pct(glob.get('mcap_chg_24h'))} 24h), BTC dominance "
              f"{glob.get('btc_dominance', 0):.1f}%. ")
    btc = cg[cg.symbol == "BTC"]
    alts = top[~top.symbol.isin(["BTC", "USDT", "USDC"])]
    if not btc.empty and not alts.empty:
        d = float(alts.chg_7d.mean() - btc.chg_7d.iloc[0])
        s += (f"Alts 7d vs BTC: {d:+.1f} pts → "
              f"{'capital rotating into alts' if d > 2 else 'BTC is holding the capital' if d < -2 else 'balanced'}. ")
    w = top.loc[top.chg_24h.idxmax()]
    lo = top.loc[top.chg_24h.idxmin()]
    s += f"Top-20 over 24h: best {w.symbol} {fmt_pct(w.chg_24h)}, worst {lo.symbol} {fmt_pct(lo.chg_24h)}."
    return s


def meme_text(df: pd.DataFrame) -> str:
    if df.empty:
        return "The radar found no tokens that pass the filters right now."
    a = df[df.grade == "A"]
    b = df[df.grade == "B"]
    s = f"Scanned {len(df)} new tokens: {len(a)} grade A, {len(b)} grade B. "
    if not a.empty:
        s += "Standouts: " + ", ".join(
            f"{r.symbol} ({r.chain}, score {r.score}, liq ${r.liq/1e3:.0f}k, {r.age_h or 0:.0f}h old)"
            for r in a.head(3).itertuples()) + ". "
    s += ("Reminder: the score measures activity and red flags, not future returns; "
          "most meme coins go to zero.")
    return s


# --------------------------------------------------------------------------- #
# LLM (optional)
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
    """Sends the question + market snapshot to Claude. Falls back without a key."""
    key = _api_key()
    if not key:
        return ("No ANTHROPIC_API_KEY is set, so I can only answer with the terminal's "
                "rules. Add the key to .streamlit/secrets.toml to enable full ASK.")
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        model = os.environ.get("FLOW_LLM_MODEL", "claude-sonnet-4-6")
        sys = ("You are the analyst of FLOW TERMINAL. Answer in English, concisely, with "
               "specific levels and numbers taken from the snapshot. Keep technical terms "
               "(RSI, ATR, drawdown) as they are. Make clear what is fact and what is "
               "estimate. Do not give personalised investment advice; describe scenarios.")
        msg = client.messages.create(
            model=model, max_tokens=800, system=sys,
            messages=[{"role": "user", "content":
                       f"SNAPSHOT (JSON):\n{json.dumps(snapshot, ensure_ascii=False, default=str)[:12000]}"
                       f"\n\nQUESTION: {question}"}])
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    except Exception as e:  # noqa: BLE001
        return f"LLM error: {e}"
