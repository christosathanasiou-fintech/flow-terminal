"""
ui/theme.py — The "terminal" look (dark background, neon violet/gold chips,
monospace font, sparkline cards). All styling lives here so you can change
colours in one place.
"""
import streamlit as st

PALETTE = {
    "bg": "#050611",
    "panel": "#0b0d1f",
    "line": "#2a2d55",
    "gold": "#f2b632",
    "violet": "#a86bff",
    "cyan": "#5ce1ff",
    "green": "#3dff8a",
    "red": "#ff4d6d",
    "text": "#e6e7ff",
    "muted": "#8b8fb8",
}

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;800&display=swap');

html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {{
    background: {PALETTE['bg']} !important;
    color: {PALETTE['text']};
}}
[data-testid="stAppViewContainer"] {{
    background:
      radial-gradient(1200px 600px at 70% -10%, rgba(168,107,255,.16), transparent 60%),
      radial-gradient(900px 500px at 0% 100%, rgba(242,182,50,.10), transparent 60%),
      {PALETTE['bg']} !important;
}}
[data-testid="stSidebar"] {{ background: {PALETTE['panel']} !important; border-right: 1px solid {PALETTE['line']}; }}
* {{ font-family: 'JetBrains Mono', ui-monospace, Menlo, Consolas, monospace !important; }}
h1,h2,h3,h4 {{ color: {PALETTE['gold']} !important; letter-spacing: .02em; }}
.block-container {{ padding-top: 3.4rem; padding-bottom: 2rem; max-width: 1500px; }}
hr {{ border-color: {PALETTE['line']} !important; }}

/* --- terminal header --- */
.ft-head {{ display:flex; justify-content:space-between; align-items:flex-end; gap:12px; flex-wrap:wrap;
            border-bottom:1px solid {PALETTE['line']}; padding-bottom:8px; margin-bottom:8px; }}
.ft-title {{ font-size:22px; font-weight:800; color:{PALETTE['gold']}; text-shadow:0 0 14px rgba(242,182,50,.45); }}
.ft-sub {{ font-size:11px; color:{PALETTE['muted']}; }}
.ft-clock {{ font-size:11px; color:{PALETTE['cyan']}; }}
.ft-live {{ display:inline-block; width:8px; height:8px; border-radius:50%; background:{PALETTE['green']};
            box-shadow:0 0 8px {PALETTE['green']}; margin-right:6px; animation: ftblink 1.4s infinite; }}
@keyframes ftblink {{ 0%,100% {{opacity:1}} 50% {{opacity:.25}} }}
@media (prefers-reduced-motion: reduce) {{ .ft-live {{ animation: none; }} }}

/* --- chips (modules) --- */
.ft-chip {{ display:inline-block; padding:3px 10px; margin:2px 4px 2px 0; border-radius:8px; font-size:11px; font-weight:600;
            border:1px solid {PALETTE['violet']}; color:{PALETTE['text']}; background:rgba(168,107,255,.08);
            box-shadow:0 0 6px rgba(168,107,255,.35); }}
.ft-chip.gold {{ border-color:{PALETTE['gold']}; box-shadow:0 0 6px rgba(242,182,50,.4); background:rgba(242,182,50,.08); }}
.ft-chip.active {{ background:{PALETTE['violet']}; color:#000; }}

/* --- sparkline cards --- */
.ft-card {{ border:1px solid {PALETTE['line']}; border-left:3px solid {PALETTE['gold']}; border-radius:8px;
            padding:6px 8px 0 8px; margin-bottom:6px; background:rgba(11,13,31,.85); }}
.ft-card.up {{ border-left-color:{PALETTE['green']}; }}
.ft-card.dn {{ border-left-color:{PALETTE['red']}; }}
.ft-card .nm {{ font-size:11px; font-weight:800; color:{PALETTE['gold']}; }}
.ft-card .tk {{ font-size:9px; color:{PALETTE['muted']}; float:right; }}
.ft-card .px {{ font-size:15px; font-weight:800; color:{PALETTE['text']}; }}
.ft-card .ch {{ font-size:11px; font-weight:600; }}
.up .ch {{ color:{PALETTE['green']}; }} .dn .ch {{ color:{PALETTE['red']}; }}

/* --- panels --- */
.ft-panel {{ border:1px solid {PALETTE['line']}; border-radius:10px; padding:10px 14px; margin:8px 0;
             background:rgba(11,13,31,.7); }}
.ft-panel.gold {{ border-color:{PALETTE['gold']}; box-shadow: inset 0 0 30px rgba(242,182,50,.05); }}
.ft-panel.violet {{ border-color:{PALETTE['violet']}; }}
.ft-label {{ font-size:11px; color:{PALETTE['gold']}; font-weight:800; margin-bottom:4px; }}
.ft-plain {{ font-size:13px; line-height:1.55; color:{PALETTE['text']}; }}
.ft-muted {{ font-size:11px; color:{PALETTE['muted']}; }}
.ft-in  {{ color:{PALETTE['green']}; font-weight:800; }}
.ft-out {{ color:{PALETTE['red']}; font-weight:800; }}
.ft-neu {{ color:{PALETTE['cyan']}; font-weight:800; }}

/* --- tape --- */
.ft-tape {{ white-space:nowrap; overflow:hidden; border-top:1px solid {PALETTE['line']}; border-bottom:1px solid {PALETTE['line']};
            padding:4px 0; font-size:11px; }}
.ft-tape .track {{ display:inline-block; padding-right:28px; animation: ftscroll 60s linear infinite; }}
.ft-tape .track span {{ display:inline; padding:0; animation:none; }}
@keyframes ftscroll {{ from {{ transform: translateX(0) }} to {{ transform: translateX(-50%) }} }}

/* --- streamlit widgets --- */
[data-testid="stTextInput"] input {{ background:#000 !important; color:{PALETTE['green']} !important; border:1px solid {PALETTE['gold']} !important;
                                     font-size:14px !important; }}
[data-testid="stTextInput"] input:focus {{ box-shadow:0 0 10px rgba(242,182,50,.5) !important; }}
div[data-testid="stDataFrame"] {{ border:1px solid {PALETTE['line']}; border-radius:8px; }}
button[kind="secondary"], button[kind="primary"] {{ border:1px solid {PALETTE['violet']} !important; background:rgba(168,107,255,.1) !important; color:{PALETTE['text']} !important; }}
[data-testid="stMetric"] {{ background:rgba(11,13,31,.7); border:1px solid {PALETTE['line']}; border-radius:8px; padding:6px 10px; }}
[data-testid="stMetricLabel"] {{ color:{PALETTE['muted']} !important; }}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
