"""
FLOW TERMINAL — το terminal που σου λέει πού κοιτάει το κεφάλαιο.

Εκκίνηση (Windows):  python -m streamlit run app.py

Δομή:
  engine/data.py      πηγές δεδομένων (yfinance, CoinGecko, DexScreener, security APIs)
  engine/rotation.py  ροή κεφαλαίου (relative strength + flow proxy + trend)
  engine/signals.py   setups LONG/SHORT/WAIT με entry/stop/target
  engine/meme.py      radar νέων meme tokens με score δικτύου/ρίσκου
  engine/narrative.py "με απλά λόγια" + προαιρετικό LLM (ASK)
  ui/theme.py         εμφάνιση terminal
  ui/components.py    κάρτες, υδρόγειος, chart, tape

Εντολές (command bar, όπως Bloomberg):
  GIP <asset>   chart + setup          π.χ. GIP GOLD, GIP NVDA, GIP BTC
  DES <asset>   περιγραφή/fundamentals  π.χ. DES US30
  SET <asset>   setup με επίπεδα         π.χ. SET OIL
  VER <asset>   "verdict" με απλά λόγια  π.χ. VER DAX
  MEME <x>      έρευνα token             π.χ. MEME WIF ή MEME <contract>
  ASK <ερώτηση> ερώτηση στον αναλυτή     π.χ. ASK τι αγοράζω σήμερα;
  BRIEF · GLOBE · COMM · STOCKS · CRYPTO · SETUPS · FX · RADAR   → module

Ενημερωτικοί σκοποί μόνο — δεν συνδέεται με broker, δεν εκτελεί εντολές.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from engine import data as D
from engine import meme as M
from engine import narrative as N
from engine import rotation as R
from engine import signals as S
from ui import components as C
from ui import theme

st.set_page_config(page_title="FLOW TERMINAL", page_icon="🌐", layout="wide",
                   initial_sidebar_state="collapsed")
theme.inject()

MODULES = ["BRIEF", "CHART", "GLOBE", "SETUPS", "STOCKS", "COMM", "CRYPTO", "RADAR", "FX", "ASK"]
MODULE_LABELS = {"BRIEF": "1 ΠΡΩΙΝΟ", "CHART": "2 CHART", "GLOBE": "3 ΥΔΡΟΓΕΙΟΣ", "SETUPS": "4 SETUPS",
                 "STOCKS": "5 ΕΤΑΙΡΕΙΕΣ", "COMM": "6 ΕΜΠΟΡΕΥΜΑΤΑ", "CRYPTO": "7 CRYPTO",
                 "RADAR": "8 MEME RADAR", "FX": "9 FX & RATES", "ASK": "ASK"}
NAMES = {a.ticker: a.name for a in D.all_assets()}
NAMES.update({"BTC-USD": "BITCOIN", "ETH-USD": "ETHEREUM", "SOL-USD": "SOLANA"})


# --------------------------------------------------------------------------- #
# Cache layer — TTL σε δευτερόλεπτα. Μικρότερο = πιο "live", περισσότερα requests.
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=300, show_spinner=False)
def load_daily(tickers: tuple[str, ...]) -> pd.DataFrame:
    return D.fetch_history(tickers, period="6mo", interval="1d")


@st.cache_data(ttl=90, show_spinner=False)
def load_intraday(tickers: tuple[str, ...]) -> pd.DataFrame:
    return D.fetch_history(tickers, period="2d", interval="15m")


@st.cache_data(ttl=120, show_spinner=False)
def load_crypto():
    return D.fetch_crypto_markets(100), D.fetch_crypto_global(), D.fetch_crypto_trending()


@st.cache_data(ttl=180, show_spinner=False)
def load_meme(with_security: bool):
    return M.scan(with_security=with_security)


@st.cache_data(ttl=600, show_spinner=False)
def load_info(ticker: str) -> dict:
    return D.fetch_quote_info(ticker)


def metrics_for(assets: list[D.Asset]) -> tuple[pd.DataFrame, pd.DataFrame]:
    hist = load_daily(tuple(a.ticker for a in assets))
    return R.asset_metrics(D.closes(hist), D.volumes(hist)), hist


def spark_rows(assets: list[D.Asset], m: pd.DataFrame, hist: pd.DataFrame, fmt: str = "{:,.2f}") -> list[dict]:
    rows = []
    for a in assets:
        if a.ticker not in m.index:
            continue
        try:
            series = hist[a.ticker]["Close"].dropna().tail(30)
        except KeyError:
            series = []
        rows.append({"name": a.name, "ticker": a.short, "price": float(m.loc[a.ticker, "last"]),
                     "chg": float(m.loc[a.ticker, "ret_1d"]), "series": series, "fmt": fmt})
    return rows


# --------------------------------------------------------------------------- #
# Κεφαλίδα + command bar
# --------------------------------------------------------------------------- #
def clocks() -> str:
    z = {"ATH": "Europe/Athens", "LDN": "Europe/London", "NY": "America/New_York", "TYO": "Asia/Tokyo"}
    return " · ".join(f"{k} {datetime.now(ZoneInfo(v)):%H:%M}" for k, v in z.items())


C.head("🌐 FLOW TERMINAL", "το terminal που σου λέει πού κοιτάει το κεφάλαιο — ενημερωτικά, όχι συμβουλή",
       clocks())

if "module" not in st.session_state:
    st.session_state.module = "BRIEF"
if "cmd_target" not in st.session_state:
    st.session_state.cmd_target = None
if "ask_q" not in st.session_state:
    st.session_state.ask_q = ""

cmd = st.text_input("ΕΝΤΟΛΗ", placeholder="π.χ. GIP GOLD · DES US30 · SET OIL · VER DAX · MEME WIF · ASK τι αγοράζω;",
                    label_visibility="collapsed", key="cmd")
if cmd:
    parts = cmd.strip().split(maxsplit=1)
    verb = parts[0].upper()
    arg = parts[1] if len(parts) > 1 else ""
    if verb in ("GIP", "DES", "SET", "VER"):
        st.session_state.module, st.session_state.cmd_target = "CHART", (verb, D.resolve_ticker(arg))
    elif verb == "MEME":
        st.session_state.module, st.session_state.cmd_target = "RADAR", ("MEME", arg)
    elif verb == "ASK":
        st.session_state.module, st.session_state.ask_q = "ASK", arg
    elif verb in MODULES:
        st.session_state.module = verb
    elif verb in ("ΠΡΩΙΝΟ", "BRIEF"):
        st.session_state.module = "BRIEF"

sel = st.pills("MODULES", MODULES, default=st.session_state.module, label_visibility="collapsed",
               format_func=lambda m: MODULE_LABELS[m], key="pills")
if sel and sel != st.session_state.module:
    st.session_state.module = sel
    st.session_state.cmd_target = None
mod = st.session_state.module

C.chips([("CORE", ""), ("ΥΔΡΟΓΕΙΟΣ", ""), ("SMART MONEY", ""), ("ROTATION", ""), ("SETUPS", ""),
         ("COMM", ""), ("CRYPTO", ""), ("MEME RADAR", ""), ("SECURITY", ""), ("FX", ""), ("ASK", "gold")],
        active={"GLOBE": "ΥΔΡΟΓΕΙΟΣ", "RADAR": "MEME RADAR", "SETUPS": "SETUPS", "COMM": "COMM",
                "CRYPTO": "CRYPTO", "ASK": "ASK"}.get(mod, "CORE"))

# tape (indices + FX + BTC) — φορτώνεται μία φορά
with st.spinner("σύνδεση με αγορές…"):
    tape_assets = D.MACRO + [D.Asset("BTC-USD", "BITCOIN", "BTC", "CRYPTO", "crypto")]
    tm, th = metrics_for(tape_assets)
C.tape([(a.short, float(tm.loc[a.ticker, "last"]), float(tm.loc[a.ticker, "ret_1d"]))
        for a in tape_assets if a.ticker in tm.index])


# =========================================================================== #
# MODULES
# =========================================================================== #
def mod_brief():
    st.markdown("### ΠΡΩΙΝΟ BRIEF — τι έγινε, πού πάει το χρήμα, τι να κοιτάξεις")
    with st.spinner("υπολογισμός ροής κεφαλαίου…"):
        mc, hc = metrics_for(D.ASSET_CLASSES + D.SECTORS)
        mr, _ = metrics_for(D.REGIONS)
        mcom, hcom = metrics_for(D.COMMODITIES)
        cg, glob, trend = load_crypto()
    classes = R.group_rotation(mc, {a.ticker: a.name for a in D.ASSET_CLASSES})
    sectors = R.group_rotation(mc, {a.ticker: a.name for a in D.SECTORS})
    regions = R.group_rotation(mr, {a.ticker: a.name for a in D.REGIONS})

    c1, c2, c3 = st.columns(3)
    C.rotation_block(c1, classes, "ΚΛΑΣΕΙΣ ΕΝΕΡΓΗΤΙΚΟΥ — ροή", "rb_classes")
    C.rotation_block(c2, sectors, "ΚΛΑΔΟΙ S&P — ροή", "rb_sectors")
    C.rotation_block(c3, regions, "ΚΕΝΤΡΑ ΑΓΟΡΑΣ — ροή", "rb_regions")

    C.panel("ΜΕ ΑΠΛΑ ΛΟΓΙΑ — ΚΛΑΣΕΙΣ", N.rotation_text(R.rotation_story(classes), R.breadth(mc), "κλάσεις"))
    C.panel("ΜΕ ΑΠΛΑ ΛΟΓΙΑ — ΚΕΝΤΡΑ", N.rotation_text(R.rotation_story(regions), R.breadth(mr), "κέντρα"), "violet")
    C.panel("ΕΜΠΟΡΕΥΜΑΤΑ", N.commodities_text(mcom, NAMES))
    C.panel("CRYPTO", N.crypto_text(cg, glob), "violet")

    st.markdown("#### ΤΑ 3 ΠΙΟ ΚΑΘΑΡΑ SETUPS ΤΗΣ ΗΜΕΡΑΣ")
    all_m = pd.concat([mc, mcom])
    hist_all = pd.concat([hc, hcom], axis=1)
    setups = [s for s in S.build_setups(hist_all, list(all_m.index), all_m) if s.direction != "WAIT"][:3]
    if not setups:
        st.info("Καμία καθαρή θέση σήμερα — WAIT σε όλα.")
    for s in setups:
        C.panel(f"{s.direction} {NAMES.get(s.ticker, s.ticker)} · conviction {s.conviction}/100",
                f"είσοδος ~{s.entry:,.2f} · stop {s.stop:,.2f} · target {s.target:,.2f} · "
                f"ATR {s.atr_pct:.1f}% · RSI {s.rsi:.0f} · {'; '.join(s.rationale)}",
                "gold" if s.direction == "LONG" else "violet")
    if trend:
        st.markdown("#### TRENDING ΣΤΟ COINGECKO (τι ψάχνει ο κόσμος τώρα)")
        C.chips([(f"{t['symbol']} #{t['rank'] or '—'}", "") for t in trend[:10]])


def mod_globe():
    st.markdown("### ΥΔΡΟΓΕΙΟΣ ΡΟΗΣ ΚΕΦΑΛΑΙΟΥ — σύρε για περιστροφή")
    with st.spinner("φόρτωση κέντρων αγοράς…"):
        mr, hr = metrics_for(D.REGIONS)
    if mr.empty:
        st.warning("Δεν ήρθαν δεδομένα από yfinance. Ξαναδοκίμασε σε λίγο.")
        return
    cen = mr.copy()
    meta = {a.ticker: a for a in D.REGIONS}
    cen["name"] = [meta[t].name for t in cen.index]
    cen["lat"] = [meta[t].lat for t in cen.index]
    cen["lon"] = [meta[t].lon for t in cen.index]
    st.plotly_chart(C.globe(cen), width="stretch", config={"displayModeBar": False}, key="globe")
    story = R.rotation_story(R.group_rotation(mr, {a.ticker: a.name for a in D.REGIONS}))
    C.panel("ΜΕ ΑΠΛΑ ΛΟΓΙΑ", N.rotation_text(story, R.breadth(mr), "κέντρα"))
    show = cen[["name", "last", "ret_1d", "ret_5d", "ret_20d", "rs_score", "flow_score", "score", "regime"]].round(2)
    show.columns = ["ΚΕΝΤΡΟ", "ETF", "1d %", "5d %", "20d %", "RS", "FLOW", "SCORE", "ΚΑΤΑΣΤΑΣΗ"]
    st.dataframe(show, width="stretch", height=420)
    st.markdown('<div class="ft-muted">Κάθε κέντρο = ETF της αγοράς σε USD. FLOW = proxy από dollar volume '
                '(δεν υπάρχει δωρεάν API πραγματικών εισροών).</div>', unsafe_allow_html=True)


def mod_chart():
    tgt = st.session_state.cmd_target or ("GIP", "GC=F")
    verb, ticker = tgt
    name = NAMES.get(ticker, ticker)
    st.markdown(f"### {verb} · {name} ({ticker})")
    with st.spinner(f"φόρτωση {ticker}…"):
        hist = load_daily((ticker,))
        universe_m, _ = metrics_for(D.COMMODITIES + D.ASSET_CLASSES + D.MACRO + D.STOCKS)
    if hist.empty or ticker not in hist.columns.get_level_values(0):
        st.error(f"Δεν βρέθηκε το «{ticker}». Δοκίμασε GOLD, OIL, US30, DAX, NVDA, BTC ή raw yfinance ticker.")
        return
    ohlc = hist[ticker].dropna(subset=["Close"])
    m = R.asset_metrics(D.closes(hist), D.volumes(hist)).loc[ticker]
    rot = float(universe_m.loc[ticker, "score"]) if ticker in universe_m.index else None
    setup = S.build_setup(ticker, ohlc, rot)
    st.plotly_chart(C.price_chart(ohlc.tail(120), name, setup), width="stretch", key="pricechart")
    if setup:
        k = st.columns(6)
        k[0].metric("ΘΕΣΗ", setup.direction)
        k[1].metric("CONVICTION", f"{setup.conviction}/100")
        k[2].metric("ΕΙΣΟΔΟΣ", f"{setup.entry:,.2f}")
        k[3].metric("STOP", f"{setup.stop:,.2f}")
        k[4].metric("TARGET", f"{setup.target:,.2f}")
        k[5].metric("RSI / ATR%", f"{setup.rsi:.0f} / {setup.atr_pct:.1f}")
    C.panel("ΜΕ ΑΠΛΑ ΛΟΓΙΑ", N.asset_text(ticker, name, m, setup))
    if verb == "DES":
        info = load_info(ticker)
        if info:
            st.markdown("#### ΠΕΡΙΓΡΑΦΗ")
            cols = st.columns(4)
            for i, (k, lbl) in enumerate([("marketCap", "Market cap"), ("trailingPE", "P/E"),
                                          ("dividendYield", "Div. yield"), ("beta", "Beta")]):
                v = info.get(k)
                cols[i].metric(lbl, f"{v/1e9:,.1f}B" if k == "marketCap" and v else (f"{v:.2f}" if v is not None else "—"))
            if info.get("longBusinessSummary"):
                st.markdown(f'<div class="ft-muted">{info["longBusinessSummary"][:900]}…</div>', unsafe_allow_html=True)


def mod_setups():
    st.markdown("### SETUPS — LONG / SHORT / WAIT σε όλο το σύμπαν")
    scope = st.radio("ΣΥΜΠΑΝ", ["Όλα", "Εμπορεύματα", "Μετοχές", "Δείκτες & FX", "Κλάδοι"], horizontal=True,
                     label_visibility="collapsed")
    uni = {"Όλα": D.COMMODITIES + D.STOCKS + D.MACRO + D.SECTORS, "Εμπορεύματα": D.COMMODITIES,
           "Μετοχές": D.STOCKS, "Δείκτες & FX": D.MACRO, "Κλάδοι": D.SECTORS}[scope]
    with st.spinner("υπολογισμός setups…"):
        m, h = metrics_for(uni)
        setups = S.build_setups(h, list(m.index), m)
    if not setups:
        st.warning("Χωρίς δεδομένα.")
        return
    df = pd.DataFrame([s.as_dict() for s in setups])
    df.insert(1, "ΟΝΟΜΑ", df["ticker"].map(NAMES).fillna(df["ticker"]))
    df["rationale"] = df["rationale"].apply(lambda r: " | ".join(r))
    show = df[["ΟΝΟΜΑ", "ticker", "direction", "conviction", "entry", "stop", "target", "rsi", "atr_pct", "trend", "rationale"]]
    show.columns = ["ΟΝΟΜΑ", "TICKER", "ΘΕΣΗ", "CONV", "ΕΙΣΟΔΟΣ", "STOP", "TARGET", "RSI", "ATR%", "ΤΑΣΗ", "ΓΙΑΤΙ"]
    st.dataframe(show, width="stretch", height=560, hide_index=True)
    n_l = (df.direction == "LONG").sum(); n_s = (df.direction == "SHORT").sum(); n_w = (df.direction == "WAIT").sum()
    C.panel("ΜΕ ΑΠΛΑ ΛΟΓΙΑ", f"{n_l} LONG, {n_s} SHORT, {n_w} WAIT. Stop = 2×ATR, target = 3×ATR (R:R 1.5). "
            f"Conviction > 60 σημαίνει ότι τάση, ορμή, όγκος και ροή κεφαλαίου συμφωνούν. "
            f"Το WAIT είναι θέση: δεν υπάρχει edge, μην κυνηγάς.")


def mod_grid(assets: list[D.Asset], title: str, key: str, cols: int = 5):
    st.markdown(f"### {title}")
    with st.spinner("φόρτωση…"):
        m, h = metrics_for(assets)
    if m.empty:
        st.warning("Χωρίς δεδομένα από yfinance.")
        return m, h
    for grp in dict.fromkeys(a.group for a in assets):
        sub = [a for a in assets if a.group == grp and a.ticker in m.index]
        if not sub:
            continue
        st.markdown(f'<div class="ft-label">{grp} ({len(sub)})</div>', unsafe_allow_html=True)
        C.card_grid(spark_rows(sub, m, h), cols=cols, key_prefix=key + grp)
    return m, h


def mod_comm():
    m, _ = mod_grid(D.COMMODITIES, "ΕΜΠΟΡΕΥΜΑΤΑ — 20 assets", "comm")
    if not m.empty:
        C.panel("ΜΕ ΑΠΛΑ ΛΟΓΙΑ", N.commodities_text(m, NAMES))
        C.rotation_block(st, m[["score"]].rename(index=NAMES), "ΡΟΗ ΑΝΑ ΕΜΠΟΡΕΥΜΑ", "rb_comm")


def mod_stocks():
    extra = st.text_input("ΠΡΟΣΘΕΣΕ TICKERS (κόμμα)", placeholder="π.χ. AMD, NFLX, OTE.AT, SIE.DE", key="extra_stocks")
    assets = list(D.STOCKS)
    for t in [x.strip().upper() for x in extra.split(",") if x.strip()]:
        assets.append(D.Asset(t, t, t, "ΔΙΚΕΣ ΣΟΥ", "equity"))
    m, h = mod_grid(assets, "ΕΤΑΙΡΕΙΕΣ — watchlist", "stk", cols=4)
    if not m.empty:
        setups = S.build_setups(h, list(m.index), m)
        top = [s for s in setups if s.direction != "WAIT"][:5]
        C.panel("ΜΕ ΑΠΛΑ ΛΟΓΙΑ", "Ισχυρότερα setups: " + ("; ".join(
            f"{s.direction} {s.ticker} ({s.conviction})" for s in top) if top else "κανένα — WAIT") +
            f". Εισροή: {', '.join(m[m.regime == 'INFLOW'].index[:5]) or '—'}. "
            f"Εκροή: {', '.join(m[m.regime == 'OUTFLOW'].index[:5]) or '—'}.")


def mod_crypto():
    st.markdown("### CRYPTO — top-100 κατά κεφαλαιοποίηση")
    with st.spinner("CoinGecko…"):
        cg, glob, trend = load_crypto()
    if cg.empty:
        st.warning("Το CoinGecko επέστρεψε κενό (rate limit). Περίμενε 60'' και πάτα R (rerun).")
        return
    k = st.columns(4)
    k[0].metric("TOTAL MCAP", f"${(glob.get('total_mcap_usd') or 0)/1e12:.2f}T", f"{glob.get('mcap_chg_24h') or 0:+.2f}% 24h")
    k[1].metric("BTC DOM", f"{glob.get('btc_dominance') or 0:.1f}%")
    k[2].metric("ETH DOM", f"{glob.get('eth_dominance') or 0:.1f}%")
    k[3].metric("TRENDING", ", ".join(t["symbol"] for t in trend[:4]) or "—")
    rows = [{"name": str(r.name)[:14].upper(), "ticker": r.symbol, "price": r.current_price,
             "chg": r.chg_24h or 0, "series": r.spark[-56:],
             "fmt": "{:,.4f}" if r.current_price < 1 else "{:,.2f}"} for r in cg.head(30).itertuples()]
    C.card_grid(rows, cols=5, key_prefix="cg")
    C.panel("ΜΕ ΑΠΛΑ ΛΟΓΙΑ", N.crypto_text(cg, glob), "violet")
    # rotation μέσα στα crypto: 7d vs 30d z-scores
    tbl = cg[["symbol", "name", "current_price", "chg_1h", "chg_24h", "chg_7d", "chg_30d", "market_cap", "total_volume"]].copy()
    tbl["vol/mcap"] = (tbl.total_volume / tbl.market_cap).round(3)
    tbl["FLOW"] = ((tbl.chg_7d.fillna(0) - tbl.chg_7d.fillna(0).mean()) / (tbl.chg_7d.std() or 1) * 0.6 +
                   (tbl["vol/mcap"] - tbl["vol/mcap"].mean()) / (tbl["vol/mcap"].std() or 1) * 0.4).round(2)
    st.markdown("#### ΡΟΗ ΜΕΣΑ ΣΤΑ CRYPTO (θετικό = προτίμηση κεφαλαίου vs το σύνολο)")
    st.dataframe(tbl.sort_values("FLOW", ascending=False).round(2), width="stretch", height=420, hide_index=True)


def mod_radar():
    st.markdown("### MEME RADAR — νέα tokens on-chain, βαθμολογημένα κατά δίκτυο & ρίσκο")
    st.markdown('<div class="ft-muted">Πηγή: DexScreener (νέα profiles + boosts) · security: RugCheck (Solana) & GoPlus (EVM). '
                'Το score μετρά δραστηριότητα και red flags — ΟΧΙ μελλοντική απόδοση.</div>', unsafe_allow_html=True)
    tgt = st.session_state.cmd_target
    if tgt and tgt[0] == "MEME" and tgt[1]:
        st.markdown(f"#### ΕΡΕΥΝΑ: {tgt[1]}")
        with st.spinner("αναζήτηση on-chain…"):
            df = M.lookup(tgt[1])
    else:
        c1, c2 = st.columns([1, 3])
        sec = c1.toggle("Έλεγχος security (πιο αργό, +20s)", value=True)
        if c2.button("↻ ΝΕΑ ΣΑΡΩΣΗ"):
            load_meme.clear()
        with st.spinner("σάρωση νέων tokens σε Solana / Base / Ethereum / BSC…"):
            df = load_meme(sec)
    if df.empty:
        st.info("Κανένα token δεν πέρασε τα φίλτρα (ή το DexScreener δεν απάντησε). Δοκίμασε ξανά σε 1'.")
        return
    C.panel("ΜΕ ΑΠΛΑ ΛΟΓΙΑ", N.meme_text(df), "violet")
    show = df[["grade", "score", "symbol", "chain", "price", "liq", "vol24", "mcap", "age_h",
               "buy_ratio_1h", "chg_1h", "chg_24h", "socials", "boosts", "security_source", "flags", "url"]].copy()
    show["flags"] = show["flags"].apply(lambda f: " | ".join(f) if f else "—")
    show.columns = ["GR", "SCORE", "SYMBOL", "CHAIN", "PRICE $", "LIQ $", "VOL24 $", "MCAP $", "AGE h",
                    "BUY% 1h", "1h %", "24h %", "SOC", "BOOST", "SEC", "RED FLAGS", "LINK"]
    st.dataframe(show, width="stretch", height=560, hide_index=True,
                 column_config={"LINK": st.column_config.LinkColumn("LINK", display_text="dexscreener"),
                                "PRICE $": st.column_config.NumberColumn(format="%.8f"),
                                "LIQ $": st.column_config.NumberColumn(format="%.0f"),
                                "VOL24 $": st.column_config.NumberColumn(format="%.0f"),
                                "MCAP $": st.column_config.NumberColumn(format="%.0f")})
    with st.expander("Πώς βγαίνει το score"):
        st.write(pd.DataFrame(df["breakdown"].tolist(), index=df["symbol"]).head(15))


def mod_fx():
    m, _ = mod_grid(D.MACRO, "FX, ΔΕΙΚΤΕΣ & ΕΠΙΤΟΚΙΑ", "fx", cols=4)
    if not m.empty:
        dxy = m.loc["DX-Y.NYB"] if "DX-Y.NYB" in m.index else None
        vix = m.loc["^VIX"] if "^VIX" in m.index else None
        txt = ""
        if dxy is not None:
            txt += (f"Δολάριο (DXY) {dxy['last']:.2f}, {N.fmt_pct(dxy['ret_5d'])} 5d → "
                    f"{'πίεση σε εμπορεύματα/EM' if dxy['ret_5d'] > 0.5 else 'ούριος άνεμος για εμπορεύματα/EM' if dxy['ret_5d'] < -0.5 else 'ουδέτερο'}. ")
        if vix is not None:
            v = vix["last"]
            txt += f"VIX {v:.1f} → {'ήρεμη αγορά, risk-on' if v < 15 else 'κανονικό' if v < 22 else 'φόβος, risk-off' if v < 30 else 'πανικός'}. "
        C.panel("ΜΕ ΑΠΛΑ ΛΟΓΙΑ", txt or "—")


def mod_ask():
    st.markdown("### ASK — ρώτα τον αναλυτή του terminal")
    q = st.text_area("ΕΡΩΤΗΣΗ", value=st.session_state.ask_q, placeholder="π.χ. Πού πάει το κεφάλαιο αυτή την εβδομάδα και τι setup έχει το ασήμι;",
                     height=90, label_visibility="collapsed")
    if st.button("ΡΩΤΑ") and q.strip():
        with st.spinner("συλλογή snapshot αγοράς…"):
            mc, hc = metrics_for(D.ASSET_CLASSES + D.SECTORS + D.COMMODITIES + D.MACRO)
            mr, _ = metrics_for(D.REGIONS)
            cg, glob, _ = load_crypto()
            setups = [s.as_dict() for s in S.build_setups(hc, list(mc.index), mc)[:12]]
            snap = {
                "ημερομηνία": datetime.now(ZoneInfo("Europe/Athens")).isoformat(timespec="minutes"),
                "ροή_κλάσεων": R.group_rotation(mc, {a.ticker: a.name for a in D.ASSET_CLASSES}).to_dict("index"),
                "ροή_κλάδων": R.group_rotation(mc, {a.ticker: a.name for a in D.SECTORS}).to_dict("index"),
                "ροή_κέντρων": R.group_rotation(mr, {a.ticker: a.name for a in D.REGIONS}).to_dict("index"),
                "εμπορεύματα": mc.loc[[t for t in mc.index if t.endswith("=F")], ["last", "ret_1d", "ret_5d", "ret_20d", "score", "regime"]].round(2).to_dict("index"),
                "top_setups": setups,
                "crypto_global": glob,
                "crypto_top10": cg.head(10)[["symbol", "current_price", "chg_24h", "chg_7d"]].round(2).to_dict("records") if not cg.empty else [],
            }
        rule = N.rotation_text(R.rotation_story(R.group_rotation(mc, {a.ticker: a.name for a in D.ASSET_CLASSES})), R.breadth(mc), "κλάσεις")
        C.panel("ΚΑΝΟΝΕΣ TERMINAL", rule)
        with st.spinner("ο αναλυτής σκέφτεται…"):
            ans = N.ask_llm(q, snap)
        C.panel("ΑΝΑΛΥΤΗΣ", ans, "violet")


# --------------------------------------------------------------------------- #
{"BRIEF": mod_brief, "CHART": mod_chart, "GLOBE": mod_globe, "SETUPS": mod_setups, "STOCKS": mod_stocks,
 "COMM": mod_comm, "CRYPTO": mod_crypto, "RADAR": mod_radar, "FX": mod_fx, "ASK": mod_ask}[mod]()

st.markdown(f'<hr><div class="ft-muted">⚠ {N.DISCLAIMER} Δεδομένα: yfinance (US μετοχές ~15\' καθυστέρηση), '
            f'CoinGecko, DexScreener. Δεν συνδέεται με broker.</div>', unsafe_allow_html=True)
