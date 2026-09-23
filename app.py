"""
FLOW TERMINAL — the terminal that shows you where capital is looking.

Launch (Windows):  python -m streamlit run app.py   (or double-click run.bat)

Structure:
  engine/data.py      data sources (yfinance, CoinGecko, DexScreener, security APIs)
  engine/rotation.py  capital rotation (relative strength + flow proxy + trend)
  engine/signals.py   LONG/SHORT/WAIT setups with entry/stop/target
  engine/meme.py      radar for new meme tokens with a network/risk score
  engine/narrative.py "in plain words" summaries + optional LLM (ASK)
  ui/theme.py         terminal look & feel
  ui/components.py    cards, globe, chart, ticker tape

Commands (command bar, Bloomberg-style):
  GIP <asset>    chart + setup             e.g. GIP GOLD, GIP NVDA, GIP BTC
  DES <asset>    description/fundamentals  e.g. DES US30
  SET <asset>    setup with levels         e.g. SET OIL
  VER <asset>    plain-words verdict       e.g. VER DAX
  MEME <x>       token lookup              e.g. MEME WIF or MEME <contract>
  ASK <question> ask the analyst           e.g. ASK what should I watch today?
  BRIEF · GLOBE · COMM · STOCKS · CRYPTO · SETUPS · FX · RADAR   → jump to module

Informational purposes only — not connected to any broker, places no orders.
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
MODULE_LABELS = {"BRIEF": "1 BRIEF", "CHART": "2 CHART", "GLOBE": "3 GLOBE", "SETUPS": "4 SETUPS",
                 "STOCKS": "5 STOCKS", "COMM": "6 COMMODITIES", "CRYPTO": "7 CRYPTO",
                 "RADAR": "8 MEME RADAR", "FX": "9 FX & RATES", "ASK": "ASK"}
NAMES = {a.ticker: a.name for a in D.all_assets()}
NAMES.update({"BTC-USD": "BITCOIN", "ETH-USD": "ETHEREUM", "SOL-USD": "SOLANA"})
PLAIN = "IN PLAIN WORDS"


# --------------------------------------------------------------------------- #
# Cache layer — TTL in seconds. Lower = more "live", but more requests.
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
    """Downloads history for a list of assets and computes rotation metrics."""
    hist = load_daily(tuple(a.ticker for a in assets))
    return R.asset_metrics(D.closes(hist), D.volumes(hist)), hist


def spark_rows(assets: list[D.Asset], m: pd.DataFrame, hist: pd.DataFrame, fmt: str = "{:,.2f}") -> list[dict]:
    """Builds the row dicts that the sparkline card grid expects."""
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
# Header + command bar
# --------------------------------------------------------------------------- #
def clocks() -> str:
    z = {"ATH": "Europe/Athens", "LDN": "Europe/London", "NY": "America/New_York", "TYO": "Asia/Tokyo"}
    return " · ".join(f"{k} {datetime.now(ZoneInfo(v)):%H:%M}" for k, v in z.items())


C.head("🌐 FLOW TERMINAL", "the terminal that shows you where capital is looking — informational, not advice",
       clocks())

if "module" not in st.session_state:
    st.session_state.module = "BRIEF"
if "cmd_target" not in st.session_state:
    st.session_state.cmd_target = None
if "ask_q" not in st.session_state:
    st.session_state.ask_q = ""

cmd = st.text_input("COMMAND", placeholder="e.g. GIP GOLD · DES US30 · SET OIL · VER DAX · MEME WIF · ASK what should I watch?",
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

sel = st.pills("MODULES", MODULES, default=st.session_state.module, label_visibility="collapsed",
               format_func=lambda m: MODULE_LABELS[m], key="pills")
if sel and sel != st.session_state.module:
    st.session_state.module = sel
    st.session_state.cmd_target = None
mod = st.session_state.module

C.chips([("CORE", ""), ("GLOBE", ""), ("SMART MONEY", ""), ("ROTATION", ""), ("SETUPS", ""),
         ("COMM", ""), ("CRYPTO", ""), ("MEME RADAR", ""), ("SECURITY", ""), ("FX", ""), ("ASK", "gold")],
        active={"GLOBE": "GLOBE", "RADAR": "MEME RADAR", "SETUPS": "SETUPS", "COMM": "COMM",
                "CRYPTO": "CRYPTO", "ASK": "ASK"}.get(mod, "CORE"))

# ticker tape (indices + FX + BTC) — loaded once per cache window
with st.spinner("connecting to markets…"):
    tape_assets = D.MACRO + [D.Asset("BTC-USD", "BITCOIN", "BTC", "CRYPTO", "crypto")]
    tm, th = metrics_for(tape_assets)
C.tape([(a.short, float(tm.loc[a.ticker, "last"]), float(tm.loc[a.ticker, "ret_1d"]))
        for a in tape_assets if a.ticker in tm.index])


# =========================================================================== #
# MODULES
# =========================================================================== #
def mod_brief():
    st.markdown("### MORNING BRIEF — what happened, where the money is going, what to watch")
    with st.spinner("computing capital flows…"):
        mc, hc = metrics_for(D.ASSET_CLASSES + D.SECTORS)
        mr, _ = metrics_for(D.REGIONS)
        mcom, hcom = metrics_for(D.COMMODITIES)
        cg, glob, trend = load_crypto()
    classes = R.group_rotation(mc, {a.ticker: a.name for a in D.ASSET_CLASSES})
    sectors = R.group_rotation(mc, {a.ticker: a.name for a in D.SECTORS})
    regions = R.group_rotation(mr, {a.ticker: a.name for a in D.REGIONS})

    c1, c2, c3 = st.columns(3)
    C.rotation_block(c1, classes, "ASSET CLASSES — flow", "rb_classes")
    C.rotation_block(c2, sectors, "S&P SECTORS — flow", "rb_sectors")
    C.rotation_block(c3, regions, "MARKET CENTRES — flow", "rb_regions")

    C.panel(f"{PLAIN} — ASSET CLASSES", N.rotation_text(R.rotation_story(classes), R.breadth(mc), "classes"))
    C.panel(f"{PLAIN} — MARKET CENTRES", N.rotation_text(R.rotation_story(regions), R.breadth(mr), "centres"), "violet")
    C.panel("COMMODITIES", N.commodities_text(mcom, NAMES))
    C.panel("CRYPTO", N.crypto_text(cg, glob), "violet")

    st.markdown("#### THE 3 CLEANEST SETUPS OF THE DAY")
    all_m = pd.concat([mc, mcom])
    hist_all = pd.concat([hc, hcom], axis=1)
    setups = [s for s in S.build_setups(hist_all, list(all_m.index), all_m) if s.direction != "WAIT"][:3]
    if not setups:
        st.info("No clean position today — WAIT on everything.")
    for s in setups:
        C.panel(f"{s.direction} {NAMES.get(s.ticker, s.ticker)} · conviction {s.conviction}/100",
                f"entry ~{s.entry:,.2f} · stop {s.stop:,.2f} · target {s.target:,.2f} · "
                f"ATR {s.atr_pct:.1f}% · RSI {s.rsi:.0f} · {'; '.join(s.rationale)}",
                "gold" if s.direction == "LONG" else "violet")
    if trend:
        st.markdown("#### TRENDING ON COINGECKO (what people are searching for right now)")
        C.chips([(f"{t['symbol']} #{t['rank'] or '—'}", "") for t in trend[:10]])


def mod_globe():
    st.markdown("### CAPITAL FLOW GLOBE — drag to rotate")
    with st.spinner("loading market centres…"):
        mr, hr = metrics_for(D.REGIONS)
    if mr.empty:
        st.warning("No data came back from yfinance. Try again in a moment.")
        return
    cen = mr.copy()
    meta = {a.ticker: a for a in D.REGIONS}
    cen["name"] = [meta[t].name for t in cen.index]
    cen["lat"] = [meta[t].lat for t in cen.index]
    cen["lon"] = [meta[t].lon for t in cen.index]
    st.plotly_chart(C.globe(cen), width="stretch", config={"displayModeBar": False}, key="globe")
    story = R.rotation_story(R.group_rotation(mr, {a.ticker: a.name for a in D.REGIONS}))
    C.panel(PLAIN, N.rotation_text(story, R.breadth(mr), "centres"))
    show = cen[["name", "last", "ret_1d", "ret_5d", "ret_20d", "rs_score", "flow_score", "score", "regime"]].round(2)
    show.columns = ["CENTRE", "ETF", "1d %", "5d %", "20d %", "RS", "FLOW", "SCORE", "STATUS"]
    st.dataframe(show, width="stretch", height=420)
    st.markdown('<div class="ft-muted">Each centre = that market\'s country ETF in USD. FLOW = proxy from dollar volume '
                '(there is no free API for actual fund flows).</div>', unsafe_allow_html=True)


def mod_chart():
    tgt = st.session_state.cmd_target or ("GIP", "GC=F")
    verb, ticker = tgt
    name = NAMES.get(ticker, ticker)
    st.markdown(f"### {verb} · {name} ({ticker})")
    with st.spinner(f"loading {ticker}…"):
        hist = load_daily((ticker,))
        universe_m, _ = metrics_for(D.COMMODITIES + D.ASSET_CLASSES + D.MACRO + D.STOCKS)
    if hist.empty or ticker not in hist.columns.get_level_values(0):
        st.error(f"Could not find “{ticker}”. Try GOLD, OIL, US30, DAX, NVDA, BTC or a raw yfinance ticker.")
        return
    ohlc = hist[ticker].dropna(subset=["Close"])
    m = R.asset_metrics(D.closes(hist), D.volumes(hist)).loc[ticker]
    rot = float(universe_m.loc[ticker, "score"]) if ticker in universe_m.index else None
    setup = S.build_setup(ticker, ohlc, rot)
    st.plotly_chart(C.price_chart(ohlc.tail(120), name, setup), width="stretch", key="pricechart")
    if setup:
        k = st.columns(6)
        k[0].metric("POSITION", setup.direction)
        k[1].metric("CONVICTION", f"{setup.conviction}/100")
        k[2].metric("ENTRY", f"{setup.entry:,.2f}")
        k[3].metric("STOP", f"{setup.stop:,.2f}")
        k[4].metric("TARGET", f"{setup.target:,.2f}")
        k[5].metric("RSI / ATR%", f"{setup.rsi:.0f} / {setup.atr_pct:.1f}")
    C.panel(PLAIN, N.asset_text(ticker, name, m, setup))
    if verb == "DES":
        info = load_info(ticker)
        if info:
            st.markdown("#### DESCRIPTION")
            cols = st.columns(4)
            for i, (k, lbl) in enumerate([("marketCap", "Market cap"), ("trailingPE", "P/E"),
                                          ("dividendYield", "Div. yield"), ("beta", "Beta")]):
                v = info.get(k)
                cols[i].metric(lbl, f"{v/1e9:,.1f}B" if k == "marketCap" and v else (f"{v:.2f}" if v is not None else "—"))
            if info.get("longBusinessSummary"):
                st.markdown(f'<div class="ft-muted">{info["longBusinessSummary"][:900]}…</div>', unsafe_allow_html=True)


def mod_setups():
    st.markdown("### SETUPS — LONG / SHORT / WAIT across the whole universe")
    scope = st.radio("UNIVERSE", ["All", "Commodities", "Stocks", "Indices & FX", "Sectors"], horizontal=True,
                     label_visibility="collapsed")
    uni = {"All": D.COMMODITIES + D.STOCKS + D.MACRO + D.SECTORS, "Commodities": D.COMMODITIES,
           "Stocks": D.STOCKS, "Indices & FX": D.MACRO, "Sectors": D.SECTORS}[scope]
    with st.spinner("computing setups…"):
        m, h = metrics_for(uni)
        setups = S.build_setups(h, list(m.index), m)
    if not setups:
        st.warning("No data.")
        return
    df = pd.DataFrame([s.as_dict() for s in setups])
    df.insert(1, "NAME", df["ticker"].map(NAMES).fillna(df["ticker"]))
    df["rationale"] = df["rationale"].apply(lambda r: " | ".join(r))
    show = df[["NAME", "ticker", "direction", "conviction", "entry", "stop", "target", "rsi", "atr_pct", "trend", "rationale"]]
    show.columns = ["NAME", "TICKER", "POSITION", "CONV", "ENTRY", "STOP", "TARGET", "RSI", "ATR%", "TREND", "WHY"]
    st.dataframe(show, width="stretch", height=560, hide_index=True)
    n_l = (df.direction == "LONG").sum()
    n_s = (df.direction == "SHORT").sum()
    n_w = (df.direction == "WAIT").sum()
    C.panel(PLAIN, f"{n_l} LONG, {n_s} SHORT, {n_w} WAIT. Stop = 2×ATR, target = 3×ATR (R:R 1.5). "
            f"Conviction > 60 means trend, momentum, volume and capital flow all agree. "
            f"WAIT is a position too: there is no edge, don't chase.")


def mod_grid(assets: list[D.Asset], title: str, key: str, cols: int = 5):
    """Generic sparkline-card module, grouped by Asset.group."""
    st.markdown(f"### {title}")
    with st.spinner("loading…"):
        m, h = metrics_for(assets)
    if m.empty:
        st.warning("No data from yfinance.")
        return m, h
    for grp in dict.fromkeys(a.group for a in assets):
        sub = [a for a in assets if a.group == grp and a.ticker in m.index]
        if not sub:
            continue
        st.markdown(f'<div class="ft-label">{grp} ({len(sub)})</div>', unsafe_allow_html=True)
        C.card_grid(spark_rows(sub, m, h), cols=cols, key_prefix=key + grp)
    return m, h


def mod_comm():
    m, _ = mod_grid(D.COMMODITIES, "COMMODITIES — 20 assets", "comm")
    if not m.empty:
        C.panel(PLAIN, N.commodities_text(m, NAMES))
        C.rotation_block(st, m[["score"]].rename(index=NAMES), "FLOW BY COMMODITY", "rb_comm")


def mod_stocks():
    extra = st.text_input("ADD TICKERS (comma-separated)", placeholder="e.g. AMD, NFLX, OTE.AT, SIE.DE", key="extra_stocks")
    assets = list(D.STOCKS)
    for t in [x.strip().upper() for x in extra.split(",") if x.strip()]:
        assets.append(D.Asset(t, t, t, "YOUR TICKERS", "equity"))
    m, h = mod_grid(assets, "STOCKS — watchlist", "stk", cols=4)
    if not m.empty:
        setups = S.build_setups(h, list(m.index), m)
        top = [s for s in setups if s.direction != "WAIT"][:5]
        C.panel(PLAIN, "Strongest setups: " + ("; ".join(
            f"{s.direction} {s.ticker} ({s.conviction})" for s in top) if top else "none — WAIT") +
            f". Inflow: {', '.join(m[m.regime == 'INFLOW'].index[:5]) or '—'}. "
            f"Outflow: {', '.join(m[m.regime == 'OUTFLOW'].index[:5]) or '—'}.")


def mod_crypto():
    st.markdown("### CRYPTO — top 100 by market cap")
    with st.spinner("CoinGecko…"):
        cg, glob, trend = load_crypto()
    if cg.empty:
        st.warning("CoinGecko returned nothing (rate limit). Wait 60 seconds and press R to rerun.")
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
    C.panel(PLAIN, N.crypto_text(cg, glob), "violet")
    # rotation inside crypto: 7d return z-score (60%) + volume/mcap z-score (40%)
    tbl = cg[["symbol", "name", "current_price", "chg_1h", "chg_24h", "chg_7d", "chg_30d", "market_cap", "total_volume"]].copy()
    tbl["vol/mcap"] = (tbl.total_volume / tbl.market_cap).round(3)
    tbl["FLOW"] = ((tbl.chg_7d.fillna(0) - tbl.chg_7d.fillna(0).mean()) / (tbl.chg_7d.std() or 1) * 0.6 +
                   (tbl["vol/mcap"] - tbl["vol/mcap"].mean()) / (tbl["vol/mcap"].std() or 1) * 0.4).round(2)
    st.markdown("#### FLOW WITHIN CRYPTO (positive = capital prefers it vs the rest)")
    st.dataframe(tbl.sort_values("FLOW", ascending=False).round(2), width="stretch", height=420, hide_index=True)


def mod_radar():
    st.markdown("### MEME RADAR — new on-chain tokens, scored by network & risk")
    st.markdown('<div class="ft-muted">Source: DexScreener (new profiles + boosts) · security: RugCheck (Solana) & GoPlus (EVM). '
                'The score measures activity and red flags — NOT future returns.</div>', unsafe_allow_html=True)
    tgt = st.session_state.cmd_target
    if tgt and tgt[0] == "MEME" and tgt[1]:
        st.markdown(f"#### LOOKUP: {tgt[1]}")
        with st.spinner("searching on-chain…"):
            df = M.lookup(tgt[1])
    else:
        c1, c2 = st.columns([1, 3])
        sec = c1.toggle("Security check (slower, +20s)", value=True)
        if c2.button("↻ NEW SCAN"):
            load_meme.clear()
        with st.spinner("scanning new tokens on Solana / Base / Ethereum / BSC…"):
            df = load_meme(sec)
    if df.empty:
        st.info("No token passed the filters (or DexScreener did not respond). Try again in 1 minute.")
        return
    C.panel(PLAIN, N.meme_text(df), "violet")
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
    with st.expander("How the score is built"):
        st.write(pd.DataFrame(df["breakdown"].tolist(), index=df["symbol"]).head(15))


def mod_fx():
    m, _ = mod_grid(D.MACRO, "FX, INDICES & RATES", "fx", cols=4)
    if not m.empty:
        dxy = m.loc["DX-Y.NYB"] if "DX-Y.NYB" in m.index else None
        vix = m.loc["^VIX"] if "^VIX" in m.index else None
        txt = ""
        if dxy is not None:
            txt += (f"US dollar (DXY) {dxy['last']:.2f}, {N.fmt_pct(dxy['ret_5d'])} 5d → "
                    f"{'pressure on commodities/EM' if dxy['ret_5d'] > 0.5 else 'tailwind for commodities/EM' if dxy['ret_5d'] < -0.5 else 'neutral'}. ")
        if vix is not None:
            v = vix["last"]
            txt += f"VIX {v:.1f} → {'calm market, risk-on' if v < 15 else 'normal' if v < 22 else 'fear, risk-off' if v < 30 else 'panic'}. "
        C.panel(PLAIN, txt or "—")


def mod_ask():
    st.markdown("### ASK — ask the terminal's analyst")
    q = st.text_area("QUESTION", value=st.session_state.ask_q,
                     placeholder="e.g. Where is capital flowing this week, and what is the setup on silver?",
                     height=90, label_visibility="collapsed")
    if st.button("ASK") and q.strip():
        with st.spinner("collecting market snapshot…"):
            mc, hc = metrics_for(D.ASSET_CLASSES + D.SECTORS + D.COMMODITIES + D.MACRO)
            mr, _ = metrics_for(D.REGIONS)
            cg, glob, _ = load_crypto()
            setups = [s.as_dict() for s in S.build_setups(hc, list(mc.index), mc)[:12]]
            snap = {
                "timestamp": datetime.now(ZoneInfo("Europe/Athens")).isoformat(timespec="minutes"),
                "asset_class_flow": R.group_rotation(mc, {a.ticker: a.name for a in D.ASSET_CLASSES}).to_dict("index"),
                "sector_flow": R.group_rotation(mc, {a.ticker: a.name for a in D.SECTORS}).to_dict("index"),
                "market_centre_flow": R.group_rotation(mr, {a.ticker: a.name for a in D.REGIONS}).to_dict("index"),
                "commodities": mc.loc[[t for t in mc.index if t.endswith("=F")], ["last", "ret_1d", "ret_5d", "ret_20d", "score", "regime"]].round(2).to_dict("index"),
                "top_setups": setups,
                "crypto_global": glob,
                "crypto_top10": cg.head(10)[["symbol", "current_price", "chg_24h", "chg_7d"]].round(2).to_dict("records") if not cg.empty else [],
            }
        rule = N.rotation_text(R.rotation_story(R.group_rotation(mc, {a.ticker: a.name for a in D.ASSET_CLASSES})), R.breadth(mc), "classes")
        C.panel("TERMINAL RULES", rule)
        with st.spinner("the analyst is thinking…"):
            ans = N.ask_llm(q, snap)
        C.panel("ANALYST", ans, "violet")


# --------------------------------------------------------------------------- #
{"BRIEF": mod_brief, "CHART": mod_chart, "GLOBE": mod_globe, "SETUPS": mod_setups, "STOCKS": mod_stocks,
 "COMM": mod_comm, "CRYPTO": mod_crypto, "RADAR": mod_radar, "FX": mod_fx, "ASK": mod_ask}[mod]()

st.markdown(f'<hr><div class="ft-muted">⚠ {N.DISCLAIMER} Data: yfinance (US stocks ~15-min delay), '
            f'CoinGecko, DexScreener. Not connected to any broker.</div>', unsafe_allow_html=True)
