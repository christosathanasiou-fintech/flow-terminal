"""
engine/meme.py — MEME RADAR: σάρωση νέων tokens on-chain και βαθμολόγηση.

Τι ΜΠΟΡΕΙ να κάνει: να βρει tokens που εμφανίστηκαν τις τελευταίες ώρες/μέρες
(DexScreener) και να τα κατατάξει με βάση μετρήσιμα κριτήρια "δικτύου":
ρευστότητα, όγκο, αγορές vs πωλήσεις, ηλικία, socials, boosts, security flags.

Τι ΔΕΝ μπορεί: να προβλέψει ποιο θα κάνει x100. Το score λέει "αυτό το token
έχει πραγματική δραστηριότητα και λιγότερα red flags", όχι "θα ανέβει".
Στα meme coins η πλειονότητα πάει στο μηδέν· το εργαλείο φιλτράρει σκουπίδια.

Score (0-100):
  liquidity   0-20   ≥$250k → 20, $50k → 10, <$10k → 0
  volume/liq  0-15   υγιές 0.5–5× (πολύ υψηλό = wash trading)
  buy ratio   0-20   buys/(buys+sells) 1h & 24h
  momentum    0-15   %5m/%1h/%6h/%24h — θετικό αλλά όχι παραβολικό
  age         0-10   6h–7d ιδανικό (πολύ νέο = ρίσκο, πολύ παλιό = "χάθηκε")
  network     0-10   website + ≥2 socials + boosts
  security    -40..0 honeypot = απόρριψη, mintable/tax → ποινή

Upgrade path:
  - Πρόσθεσε holder distribution (Helius για Solana, Moralis για EVM).
  - Κράτα ιστορικό των scores σε SQLite και μέτρα το forward return 24h/72h
    ανά bucket score → έτσι αποδεικνύεις (ή διαψεύδεις) ότι το score έχει edge.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd

from . import data as D


def _num(x, default=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _age_hours(pair: dict) -> float | None:
    ts = pair.get("pairCreatedAt")
    if not ts:
        return None
    return (time.time() * 1000 - float(ts)) / 3.6e6


def score_pair(pair: dict, sec: dict | None = None) -> dict:
    """Βαθμολογεί ένα DexScreener pair. Επιστρέφει dict με score + breakdown."""
    liq = _num((pair.get("liquidity") or {}).get("usd"))
    vol24 = _num((pair.get("volume") or {}).get("h24"))
    vol1 = _num((pair.get("volume") or {}).get("h1"))
    tx = pair.get("txns") or {}
    b1, s1 = _num((tx.get("h1") or {}).get("buys")), _num((tx.get("h1") or {}).get("sells"))
    b24, s24 = _num((tx.get("h24") or {}).get("buys")), _num((tx.get("h24") or {}).get("sells"))
    pc = pair.get("priceChange") or {}
    c5, c1, c6, c24 = (_num(pc.get("m5")), _num(pc.get("h1")), _num(pc.get("h6")), _num(pc.get("h24")))
    age = _age_hours(pair)
    info = pair.get("info") or {}
    n_soc = len(info.get("socials") or [])
    n_web = len(info.get("websites") or [])
    boosts = _num((pair.get("boosts") or {}).get("active"))
    fdv = _num(pair.get("fdv")); mcap = _num(pair.get("marketCap"))

    flags: list[str] = []
    # liquidity
    if liq >= 250_000: s_liq = 20
    elif liq >= 100_000: s_liq = 15
    elif liq >= 50_000: s_liq = 10
    elif liq >= 10_000: s_liq = 4
    else: s_liq = 0; flags.append("ρευστότητα < $10k")
    # volume/liquidity
    ratio = vol24 / liq if liq > 0 else 0
    if 0.5 <= ratio <= 5: s_vl = 15
    elif 5 < ratio <= 15: s_vl = 8
    elif ratio > 15: s_vl = 2; flags.append("όγκος/ρευστότητα > 15× (πιθανό wash trading)")
    else: s_vl = 3
    # buy pressure
    br1 = b1 / (b1 + s1) if (b1 + s1) > 0 else 0.5
    br24 = b24 / (b24 + s24) if (b24 + s24) > 0 else 0.5
    s_buy = round(10 * min(1, max(0, (br1 - 0.4) / 0.4)) + 10 * min(1, max(0, (br24 - 0.4) / 0.4)))
    if (b24 + s24) < 50:
        s_buy = min(s_buy, 5); flags.append("λιγότερα από 50 txns/24h")
    # momentum
    s_mom = 0
    for chg, w in ((c1, 5), (c6, 5), (c24, 5)):
        if 0 < chg <= 150: s_mom += w
        elif chg > 150: s_mom += 1; flags.append(f"παραβολική κίνηση {chg:+.0f}%")
        elif -30 <= chg <= 0: s_mom += 2
    # age
    if age is None: s_age = 3
    elif 6 <= age <= 168: s_age = 10
    elif 1 <= age < 6: s_age = 6; flags.append("ηλικία < 6 ωρών")
    elif age < 1: s_age = 2; flags.append("ηλικία < 1 ώρας — εξαιρετικά ρίσκο")
    elif age <= 720: s_age = 6
    else: s_age = 2
    # network
    s_net = min(10, 3 * n_web + 2 * min(n_soc, 3) + (1 if boosts > 0 else 0))
    if n_soc == 0 and n_web == 0: flags.append("χωρίς website/socials")
    # security
    s_sec = 0
    sec = sec or {}
    if sec.get("honeypot"):
        s_sec = -100; flags.append("HONEYPOT — ΑΠΟΡΡΙΨΗ")
    else:
        if sec.get("mintable"): s_sec -= 15; flags.append("mintable supply")
        if sec.get("owner_can_change_tax"): s_sec -= 10; flags.append("owner αλλάζει tax")
        st = max(_num(sec.get("buy_tax")), _num(sec.get("sell_tax")))
        if st > 10: s_sec -= 15; flags.append(f"tax {st:.0f}%")
        for r in sec.get("risks") or []:
            if any(k in r.lower() for k in ("freeze", "mutable", "low liquidity", "top 10")):
                s_sec -= 5; flags.append(r)

    total = max(0, min(100, s_liq + s_vl + s_buy + s_mom + s_age + s_net + s_sec))
    grade = "A" if total >= 75 else "B" if total >= 60 else "C" if total >= 45 else "D"
    base = pair.get("baseToken") or {}
    return {
        "symbol": base.get("symbol", "?"), "name": base.get("name", ""),
        "chain": pair.get("chainId"), "address": base.get("address"),
        "dex": pair.get("dexId"), "url": pair.get("url"),
        "price": _num(pair.get("priceUsd")), "liq": liq, "vol24": vol24, "vol1": vol1,
        "mcap": mcap or fdv, "age_h": round(age, 1) if age is not None else None,
        "buy_ratio_1h": round(br1, 2), "buy_ratio_24h": round(br24, 2),
        "chg_5m": c5, "chg_1h": c1, "chg_6h": c6, "chg_24h": c24,
        "socials": n_soc, "websites": n_web, "boosts": int(boosts),
        "score": total, "grade": grade, "flags": flags,
        "breakdown": {"liq": s_liq, "vol/liq": s_vl, "buys": s_buy, "mom": s_mom,
                      "age": s_age, "net": s_net, "sec": s_sec},
        "security_source": sec.get("source", "—"),
    }


def scan(max_tokens: int = 60, chains: tuple[str, ...] = ("solana", "base", "ethereum", "bsc"),
         with_security: bool = True, min_liq: float = 5_000) -> pd.DataFrame:
    """
    Πλήρης σάρωση: υποψήφια → pairs → security → score. Επιστρέφει DataFrame
    ταξινομημένο κατά score. Χρόνος: ~10-40s ανάλογα με το with_security.
    """
    cands = D.fetch_dex_candidates()
    by_chain: dict[str, list[str]] = {}
    for c in cands:
        ch = c.get("chainId")
        if ch in chains:
            by_chain.setdefault(ch, []).append(c["tokenAddress"])
    rows = []
    for ch, addrs in by_chain.items():
        pairs = D.fetch_dex_pairs(ch, addrs[:max_tokens])
        # κρατάμε το pair με τη μεγαλύτερη ρευστότητα ανά token
        best: dict[str, dict] = {}
        for p in pairs:
            a = (p.get("baseToken") or {}).get("address")
            if not a:
                continue
            if a not in best or _num((p.get("liquidity") or {}).get("usd")) > _num((best[a].get("liquidity") or {}).get("usd")):
                best[a] = p
        for a, p in best.items():
            if _num((p.get("liquidity") or {}).get("usd")) < min_liq:
                continue
            sec = D.token_security(ch, a) if with_security else {}
            rows.append(score_pair(p, sec))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("score", ascending=False).reset_index(drop=True)


def lookup(query: str) -> pd.DataFrame:
    """Έρευνα συγκεκριμένου token με όνομα/σύμβολο/διεύθυνση (εντολή MEME <x>)."""
    pairs = D.dex_search(query)
    rows = []
    for p in pairs[:15]:
        base = p.get("baseToken") or {}
        sec = D.token_security(p.get("chainId", ""), base.get("address", "")) if base.get("address") else {}
        rows.append(score_pair(p, sec))
    df = pd.DataFrame(rows)
    return df.sort_values("score", ascending=False).reset_index(drop=True) if not df.empty else df
