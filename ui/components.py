"""
ui/components.py — Επαναχρησιμοποιήσιμα κομμάτια οθόνης (Plotly + HTML).
"""
from __future__ import annotations

import html

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .theme import PALETTE as P

_LAYOUT = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
               font=dict(family="JetBrains Mono, monospace", color=P["text"], size=11),
               margin=dict(l=8, r=8, t=8, b=8))


# --------------------------------------------------------------------------- #
def head(title: str, subtitle: str, clocks: str) -> None:
    st.markdown(
        f'<div class="ft-head"><div><div class="ft-title">{title}</div>'
        f'<div class="ft-sub">{subtitle}</div></div>'
        f'<div class="ft-clock"><span class="ft-live"></span>LIVE · {clocks}</div></div>',
        unsafe_allow_html=True)


def chips(items: list[tuple[str, str]], active: str = "") -> None:
    """items: [(label, style)] style ∈ {'', 'gold'}"""
    out = "".join(f'<span class="ft-chip {s} {"active" if l == active else ""}">{html.escape(l)}</span>'
                  for l, s in items)
    st.markdown(out, unsafe_allow_html=True)


def panel(label: str, body: str, style: str = "gold") -> None:
    st.markdown(f'<div class="ft-panel {style}"><div class="ft-label">{html.escape(label)}</div>'
                f'<div class="ft-plain">{html.escape(body)}</div></div>', unsafe_allow_html=True)


def tape(items: list[tuple[str, float, float]]) -> None:
    """items: [(label, last, chg_pct)] — κυλιόμενη ταινία τιμών."""
    if not items:
        return
    parts = []
    for lbl, last, chg in items:
        col = P["green"] if chg >= 0 else P["red"]
        parts.append(f'<b style="color:{P["gold"]}">{html.escape(lbl)}</b> {last:,.2f} '
                     f'<span style="color:{col}">{chg:+.2f}%</span>')
    s = " &nbsp;·&nbsp; ".join(parts)
    st.markdown(f'<div class="ft-tape"><span class="track">{s} &nbsp;·&nbsp; {s}</span></div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
def sparkline(series, up: bool, height: int = 48) -> go.Figure:
    y = np.asarray(list(series), dtype=float)
    y = y[~np.isnan(y)]
    col = P["green"] if up else P["red"]
    fig = go.Figure(go.Scatter(y=y, mode="lines", line=dict(color=col, width=1.6)))
    fig.update_layout(**_LAYOUT, height=height, showlegend=False,
                      xaxis=dict(visible=False), yaxis=dict(visible=False, range=[y.min() * 0.995, y.max() * 1.005] if len(y) else None))
    return fig


def card(name: str, ticker: str, price: float, chg: float, series, key: str,
         price_fmt: str = "{:,.2f}") -> None:
    up = chg >= 0
    st.markdown(f'<div class="ft-card {"up" if up else "dn"}"><span class="tk">{html.escape(ticker)}</span>'
                f'<div class="nm">{html.escape(name)}</div><div class="px">{price_fmt.format(price)}</div>'
                f'<div class="ch">{chg:+.2f}%</div></div>', unsafe_allow_html=True)
    st.plotly_chart(sparkline(series, up), width="stretch", key=key,
                    config={"displayModeBar": False, "staticPlot": True})


def card_grid(rows: list[dict], cols: int = 5, key_prefix: str = "g") -> None:
    """rows: [{name, ticker, price, chg, series, fmt?}]"""
    for i in range(0, len(rows), cols):
        cs = st.columns(cols)
        for c, r in zip(cs, rows[i:i + cols]):
            with c:
                card(r["name"], r["ticker"], r["price"], r["chg"], r["series"],
                     key=f"{key_prefix}_{r['ticker']}_{i}", price_fmt=r.get("fmt", "{:,.2f}"))


# --------------------------------------------------------------------------- #
def price_chart(ohlc: pd.DataFrame, title: str, setup=None) -> go.Figure:
    """Candlestick + SMA20/50 + επίπεδα entry/stop/target."""
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=ohlc.index, open=ohlc["Open"], high=ohlc["High"],
                                 low=ohlc["Low"], close=ohlc["Close"], name=title,
                                 increasing_line_color=P["green"], decreasing_line_color=P["red"]))
    c = ohlc["Close"]
    fig.add_trace(go.Scatter(x=ohlc.index, y=c.rolling(20).mean(), name="SMA20",
                             line=dict(color=P["cyan"], width=1)))
    fig.add_trace(go.Scatter(x=ohlc.index, y=c.rolling(50).mean(), name="SMA50",
                             line=dict(color=P["violet"], width=1)))
    if setup is not None and setup.direction != "WAIT":
        for y, lbl, col in ((setup.entry, "ENTRY", P["gold"]), (setup.stop, "STOP", P["red"]),
                            (setup.target, "TARGET", P["green"])):
            fig.add_hline(y=y, line=dict(color=col, width=1, dash="dot"),
                          annotation_text=f"{lbl} {y:,.2f}", annotation_font_color=col)
    fig.update_layout(**_LAYOUT, height=420, xaxis_rangeslider_visible=False,
                      legend=dict(orientation="h", y=1.02, x=0),
                      xaxis=dict(gridcolor=P["line"]), yaxis=dict(gridcolor=P["line"]))
    return fig


def globe(centers: pd.DataFrame) -> go.Figure:
    """
    centers: index=ticker, στήλες name, lat, lon, score, regime, ret_5d.
    3D υδρόγειος (ορθογραφική προβολή) — μέγεθος/χρώμα = ροή κεφαλαίου.
    """
    if centers.empty:
        return go.Figure()
    col = np.where(centers["regime"] == "INFLOW", P["green"],
                   np.where(centers["regime"] == "OUTFLOW", P["red"], P["cyan"]))
    size = 8 + centers["score"].abs().clip(0, 100) / 100 * 22
    txt = [f"{n} {s:+.0f}" for n, s in zip(centers["name"], centers["score"])]
    hover = [f"{n}<br>score {s:+.0f} · 5d {r:+.1f}% · {rg}"
             for n, s, r, rg in zip(centers["name"], centers["score"], centers["ret_5d"], centers["regime"])]
    fig = go.Figure(go.Scattergeo(
        lat=centers["lat"], lon=centers["lon"], text=txt, hovertext=hover, hoverinfo="text",
        mode="markers+text", textposition="top center", textfont=dict(size=9, color=P["text"]),
        marker=dict(size=size, color=col, opacity=.9, line=dict(width=1, color="#fff"))))
    # τόξα ροής: από τα 3 χειρότερα προς τα 3 καλύτερα
    srt = centers.sort_values("score")
    for _, a in srt.head(3).iterrows():
        for _, b in srt.tail(3).iterrows():
            fig.add_trace(go.Scattergeo(lat=[a.lat, b.lat], lon=[a.lon, b.lon], mode="lines",
                                        line=dict(width=1, color="rgba(242,182,50,.45)"),
                                        hoverinfo="skip", showlegend=False))
    fig.update_geos(projection_type="orthographic", showcountries=True, countrycolor="#1e2148",
                    showland=True, landcolor="#0e1130", showocean=True, oceancolor="#070818",
                    showcoastlines=True, coastlinecolor="#2a2d55", bgcolor="rgba(0,0,0,0)",
                    projection_rotation=dict(lon=20, lat=25), showframe=False)
    fig.update_layout(**_LAYOUT, height=520, showlegend=False)
    return fig


def rotation_bars(g: pd.DataFrame, title: str) -> go.Figure:
    if g.empty:
        return go.Figure()
    col = np.where(g["score"] >= 0, P["green"], P["red"])
    fig = go.Figure(go.Bar(x=g["score"], y=g.index, orientation="h", marker_color=col,
                           text=[f"{s:+.0f}" for s in g["score"]], textposition="outside"))
    fig.update_layout(**_LAYOUT, height=max(260, 22 * len(g) + 20),
                      xaxis=dict(range=[-110, 110], gridcolor=P["line"], zerolinecolor=P["gold"]),
                      yaxis=dict(autorange="reversed"))
    return fig


def rotation_block(container, g: pd.DataFrame, title: str, key: str) -> None:
    """Τίτλος ως HTML label ΠΑΝΩ από το γράφημα (ο Plotly title κοβόταν)."""
    container.markdown(f'<div class="ft-label">{html.escape(title)}</div>', unsafe_allow_html=True)
    container.plotly_chart(rotation_bars(g, title), width="stretch", key=key, config={"displayModeBar": False})


def regime_tag(r: str) -> str:
    cls = {"INFLOW": "ft-in", "OUTFLOW": "ft-out"}.get(r, "ft-neu")
    return f'<span class="{cls}">{r}</span>'
