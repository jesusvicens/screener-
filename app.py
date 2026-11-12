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


base, mk = cargar("base.parquet"), cargar("mercado.parquet")
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

cfg = {}
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

st.markdown(f"**{len(tabla):,} empresas**".replace(",", "."))
st.dataframe(vista, column_config=cfg, hide_index=True, width="stretch", height=650)
st.download_button("Descargar CSV", tabla.to_csv(index=False).encode("utf-8"), "screener.csv", "text/csv")
