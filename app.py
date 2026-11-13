"""Screener sencillo de cotizadas de EE. UU. con datos públicos (SEC + Nasdaq)."""
from __future__ import annotations

import io
import os
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

from screener import datos

st.set_page_config(page_title="Screener", layout="wide")

REPO = os.environ.get("SCREENER_REPO", "jesusvicens/screener-")
LOCAL = Path(__file__).parent / "out"


@st.cache_data(ttl=6 * 3600, show_spinner="Cargando datos…")
def cargar(nombre: str) -> pd.DataFrame | None:
    p = LOCAL / nombre
    if p.exists():
        return pd.read_parquet(p)
    try:
        r = requests.get(f"https://raw.githubusercontent.com/{REPO}/datos/{nombre}", timeout=60)
        return pd.read_parquet(io.BytesIO(r.content)) if r.status_code == 200 else None
    except requests.RequestException:
        return None


# ---------------------------------------------------------------- ficha de empresa (se abre en otra pestaña: ?ticker=XXX)
def ficha(df: pd.DataFrame, t: str):
    fila = df[df["Ticker"] == t]
    if fila.empty:
        st.error(f"No encuentro {t}.")
        return
    r = fila.iloc[0]
    st.title(f"{r['Empresa']} ({t})")
    st.caption(" · ".join(str(x) for x in (r.get("Sector"), r.get("Industria"), r.get("Mercado")) if x and x != "—"))

    def fmt(m):
        v = pd.to_numeric(pd.Series([r.get(m)]), errors="coerce").iloc[0]
        if pd.isna(v):
            return "—"
        k = datos.KIND.get(m)
        if k == "pct":
            return f"{v * 100:.1f} %".replace(".", ",")
        if k == "x":
            return f"{v:.1f}".replace(".", ",")
        if k == "m":
            return f"{v:,.0f}".replace(",", ".")
        if k == "ps":
            return f"{v:.2f}".replace(".", ",")
        return f"{v:.0f}"

    c = st.columns(5)
    for col, m in zip(c, ["Precio", "Capitalización (M$)", "PER", "P/FCF", "Rent. dividendo"]):
        col.metric(m, fmt(m))

    Y = int(r["Año datos"])
    serie = lambda k: [] if r.get(k) is None else list(r.get(k))  # noqa: E731
    rev, eps = serie("_s_rev"), serie("_s_eps")
    anos = [str(Y - len(rev) + 1 + i) for i in range(len(rev))]
    hist = pd.DataFrame({"Año": anos, "Ventas (M$)": [None if (x is None or pd.isna(x)) else x / 1e6 for x in rev],
                         "BPA diluido ($)": [None if (x is None or pd.isna(x)) else x for x in eps]}).set_index("Año")
    g = st.columns(2)
    g[0].markdown("**Ventas (M$)**")
    g[0].bar_chart(hist["Ventas (M$)"])
    g[1].markdown("**BPA diluido ($)**")
    g[1].bar_chart(hist["BPA diluido ($)"])

    grupos: dict[str, list[str]] = {}
    for m, grupo, _k, _d in datos.METRICS:
        if grupo not in ("Tamaño",) and m not in ("Precio",):
            grupos.setdefault(grupo, []).append(m)
    cols = st.columns(3)
    for i, (grupo, ms) in enumerate(grupos.items()):
        with cols[i % 3]:
            st.markdown(f"**{grupo}**")
            st.dataframe(pd.DataFrame({"": ms, "Valor": [fmt(m) for m in ms]}).set_index(""), width="stretch")
    st.caption(f"Cuentas de la SEC del ejercicio {Y}; precio de Nasdaq.")


base, mk = cargar("base.parquet"), cargar("mercado.parquet")
if "ticker" in st.query_params and base is not None:
    ficha(datos.combine(base, mk), st.query_params["ticker"].upper())
    st.stop()
st.title("Screener")
if base is None:
    st.warning("Aún no hay datos. Se generan cada noche con GitHub Actions (o ejecuta `python actualizar.py`).")
    st.stop()
df = datos.combine(base, mk)
st.caption(f"{len(df):,} empresas de EE. UU. · cuentas de la SEC (ejercicio {int(df['Año datos'].max())}) · precios de Nasdaq".replace(",", "."))

# ---------------------------------------------------------------- filtros
c = st.columns([2, 3])
texto = c[0].text_input("Buscar", placeholder="Ticker o nombre")
sectores = c[1].multiselect("Sector", sorted(x for x in df["Sector"].dropna().unique() if x != "—"))

FILTROS = [  # (métrica, etiqueta, mínimo por defecto, máximo por defecto, paso); porcentajes en %
    ("Ventas (M$)", "Ventas mín. (M$)", 0.0, None, 100.0),
    ("CAGR ventas 5a", "Crec. ventas 5a mín. (%)", None, None, 1.0),
    ("CAGR BPA 5a", "Crec. BPA 5a mín. (%)", None, None, 1.0),
    ("Margen operativo", "Margen operativo mín. (%)", None, None, 1.0),
    ("ROE", "ROE mín. (%)", None, None, 1.0),
    ("Deuda / patrimonio", "Deuda / patrimonio máx.", None, None, 0.1),
    ("PER", "PER máx.", None, None, 1.0),
]
filtros = {}
cols = st.columns(len(FILTROS))
for col, (m, etiqueta, _lo, _hi, paso) in zip(cols, FILTROS):
    v = col.number_input(etiqueta, value=None, step=paso, placeholder="—")
    if v is None:
        continue
    if datos.KIND[m] == "pct":
        v = v / 100
    filtros[m] = (None, v) if "máx" in etiqueta else (v, None)

res = datos.apply_filters(df, filtros, texto, sectores)

# ---------------------------------------------------------------- tabla
COLS = ["Ticker", "Empresa", "Sector", "Precio", "Capitalización (M$)", "Ventas (M$)", "CAGR ventas 5a", "CAGR BPA 5a",
        "Margen operativo", "ROE", "ROIC", "Deuda / patrimonio", "PER", "P/FCF", "Rent. dividendo"]
tabla = res[COLS].sort_values("Capitalización (M$)", ascending=False, na_position="last").reset_index(drop=True)
vista = tabla.copy()
for m in COLS:
    if m in datos.KIND:
        vista[m] = pd.to_numeric(vista[m], errors="coerce") * (100 if datos.KIND[m] == "pct" else 1)

vista["Ticker"] = "?ticker=" + vista["Ticker"].astype(str)
cfg = {"Ticker": st.column_config.LinkColumn("Ticker", display_text=r"\?ticker=(.*)", help="Abre la ficha en otra pestaña")}
for m in COLS:
    k = datos.KIND.get(m)
    if k == "pct":
        cfg[m] = st.column_config.NumberColumn(m, format="%.1f %%", help=datos.HELP.get(m))
    elif k == "x":
        cfg[m] = st.column_config.NumberColumn(m, format="%.1f", help=datos.HELP.get(m))
    elif k == "m":
        cfg[m] = st.column_config.NumberColumn(m, format="%,.0f", help=datos.HELP.get(m))
    elif k == "ps":
        cfg[m] = st.column_config.NumberColumn(m, format="%.2f", help=datos.HELP.get(m))

st.markdown(f"**{len(tabla):,} empresas** · pulsa un ticker para abrir su ficha".replace(",", ".", 1))
st.dataframe(vista, column_config=cfg, hide_index=True, width="stretch", height=650)
st.download_button("Descargar CSV", tabla.to_csv(index=False).encode("utf-8"), "screener.csv", "text/csv")
