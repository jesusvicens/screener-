"""Tabla de fundamentales de todas las cotizadas de EE. UU. (SEC) más precios y sectores (Nasdaq).

Con ~100 llamadas a los «frames» de la SEC se monta una tabla de ~5.000 empresas con crecimientos, márgenes,
rentabilidad, salud financiera y política de capital. Con el precio se añaden los ratios de valoración.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import requests

from . import sec

REVENUE_TAGS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax"]
SPLIT_FACTORS = [1.5, 2, 3, 4, 5, 6, 7, 8, 10, 15, 20, 25, 30, 40, 50,
                 1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 8, 1 / 10, 1 / 15, 1 / 20, 1 / 25, 1 / 30, 1 / 50]

# (columna, grupo, formato, explicación). formato: pct, x (múltiplo), m (millones), ps (por acción), int
METRICS: list[tuple[str, str, str, str]] = [
    ("Capitalización (M$)", "Tamaño", "m", "Precio × acciones"),
    ("Valor empresa (M$)", "Tamaño", "m", "Capitalización + deuda financiera − caja"),
    ("Ventas (M$)", "Tamaño", "m", "Ventas del último ejercicio"),
    ("Beneficio (M$)", "Tamaño", "m", "Beneficio neto del último ejercicio"),
    ("Crec. ventas 1a", "Crecimiento", "pct", "Ventas último año / año anterior − 1"),
    ("CAGR ventas 3a", "Crecimiento", "pct", "Crecimiento anual compuesto de las ventas, 3 años"),
    ("CAGR ventas 5a", "Crecimiento", "pct", "Crecimiento anual compuesto de las ventas, 5 años"),
    ("Crec. BPA 1a", "Crecimiento", "pct", "BPA diluido último año / año anterior − 1 (ajustado por splits)"),
    ("CAGR BPA 3a", "Crecimiento", "pct", "Crecimiento anual compuesto del BPA, 3 años"),
    ("CAGR BPA 5a", "Crecimiento", "pct", "Crecimiento anual compuesto del BPA, 5 años"),
    ("Crec. medio ventas", "Crecimiento", "pct", "Media de los crecimientos anuales de las ventas en los últimos N años"),
    ("Crec. medio BPA", "Crecimiento", "pct", "Media de los crecimientos anuales del BPA en los últimos N años"),
    ("CAGR beneficio 5a", "Crecimiento", "pct", "Crecimiento anual compuesto del beneficio neto, 5 años"),
    ("CAGR FCF 5a", "Crecimiento", "pct", "Crecimiento anual compuesto del flujo de caja libre, 5 años"),
    ("Años caída ventas", "Consistencia", "int", "Años (de 5) en que las ventas bajaron"),
    ("Años caída BPA", "Consistencia", "int", "Años (de 5) en que el BPA bajó"),
    ("Años con pérdidas", "Consistencia", "int", "Años (de 6) con beneficio neto negativo"),
    ("Margen bruto", "Márgenes", "pct", "Margen bruto / ventas"),
    ("Margen operativo", "Márgenes", "pct", "Resultado operativo / ventas"),
    ("Margen neto", "Márgenes", "pct", "Beneficio neto / ventas"),
    ("Margen FCF", "Márgenes", "pct", "(Flujo operativo − capex) / ventas"),
    ("I+D / ventas", "Márgenes", "pct", "Gasto en I+D / ventas"),
    ("SBC / ventas", "Márgenes", "pct", "Remuneración en acciones / ventas"),
    ("ROE", "Rentabilidad", "pct", "Beneficio neto / patrimonio"),
    ("ROE medio 5a", "Rentabilidad", "pct", "Media de los últimos 5 ROE"),
    ("ROA", "Rentabilidad", "pct", "Beneficio neto / activo total"),
    ("ROIC", "Rentabilidad", "pct", "EBIT × (1 − tipo efectivo) / (deuda + patrimonio − caja)"),
    ("Deuda / patrimonio", "Salud", "x", "Deuda financiera / patrimonio"),
    ("Deuda neta / EBITDA", "Salud", "x", "(Deuda − caja) / EBITDA"),
    ("Liquidez corriente", "Salud", "x", "Activo corriente / pasivo corriente"),
    ("Var. acciones 5a", "Capital", "pct", "Variación anual de las acciones diluidas (− = recompra neta)"),
    ("Payout", "Capital", "pct", "Dividendos / beneficio neto"),
    ("Recompras / FCF", "Capital", "pct", "Recompras / flujo de caja libre"),
    ("FCF / beneficio", "Capital", "pct", "Flujo de caja libre / beneficio neto"),
    ("Capex / OCF", "Capital", "pct", "Capex / flujo operativo"),
    ("Precio", "Valoración", "ps", "Último cierre"),
    ("PER", "Valoración", "x", "Precio / BPA diluido del último ejercicio"),
    ("PEG", "Valoración", "x", "PER / (CAGR BPA 5a × 100)"),
    ("P/Ventas", "Valoración", "x", "Capitalización / ventas"),
    ("P/Valor contable", "Valoración", "x", "Capitalización / patrimonio"),
    ("P/FCF", "Valoración", "x", "Capitalización / flujo de caja libre"),
    ("EV/EBIT", "Valoración", "x", "Valor empresa / resultado operativo"),
    ("EV/EBITDA", "Valoración", "x", "Valor empresa / EBITDA"),
    ("Rent. FCF", "Valoración", "pct", "Flujo de caja libre / capitalización"),
    ("Rent. dividendo", "Valoración", "pct", "Dividendos pagados / capitalización"),
]
KIND = {m: k for m, _g, k, _d in METRICS}
HELP = {m: d for m, _g, _k, d in METRICS}
AVG_GROWTH = {"Crec. medio ventas": "_s_rev", "Crec. medio BPA": "_s_eps"}


# ---------------------------------------------------------------- utilidades
def _cagr(a, b, n):
    return (a / b) ** (1 / n) - 1 if (a and b and a > 0 and b > 0 and n > 0) else None


def _d(a, b):
    return a / b if (a is not None and b not in (None, 0)) else None


def _split(ratio):
    if not ratio or 0.6 < ratio < 1.7:
        return None
    best = min(SPLIT_FACTORS, key=lambda f: abs(ratio / f - 1))
    return best if abs(ratio / best - 1) < 0.12 else None


def _merged(tags, period, unit="USD"):
    out: dict[int, float] = {}
    for t in tags:
        for cik, v in sec.frame(t, period, unit).items():
            out.setdefault(cik, v)
    return out


def latest_year() -> int:
    """Último año natural con suficientes cuentas presentadas."""
    y = date.today().year - 1
    if len(sec.frame("NetIncomeLoss", f"CY{y}")) < 4000:
        y -= 1
    return y


# ---------------------------------------------------------------- fundamentales (SEC)
def build_base(years_back: int = 10, log=print) -> pd.DataFrame:
    Y = latest_year()
    yrs = list(range(Y - years_back, Y + 1))
    hist = {
        "rev": (REVENUE_TAGS, "", "USD"), "ni": (["NetIncomeLoss", "ProfitLoss"], "", "USD"),
        "eps": (["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"], "", "USD-per-shares"),
        "ocf": (["NetCashProvidedByUsedInOperatingActivities"], "", "USD"),
        "capex": (["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"], "", "USD"),
        "sh": (["WeightedAverageNumberOfDilutedSharesOutstanding"], "", "shares"),
        "eq": (["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"], "Q4I", "USD"),
        "op": (["OperatingIncomeLoss"], "", "USD"),
    }
    last = {
        "gp": (["GrossProfit"], ""), "assets": (["Assets"], "Q4I"), "ac": (["AssetsCurrent"], "Q4I"), "lc": (["LiabilitiesCurrent"], "Q4I"),
        "cash": (["CashCashEquivalentsAndShortTermInvestments", "CashAndCashEquivalentsAtCarryingValue"], "Q4I"),
        "ltd": (["LongTermDebtNoncurrent", "LongTermDebt"], "Q4I"), "std": (["LongTermDebtCurrent", "DebtCurrent"], "Q4I"),
        "div": (["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"], ""), "bb": (["PaymentsForRepurchaseOfCommonStock"], ""),
        "da": (["DepreciationDepletionAndAmortization", "DepreciationAndAmortization"], ""), "tax": (["IncomeTaxExpenseBenefit"], ""),
        "pretax": (["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"], ""),
        "rnd": (["ResearchAndDevelopmentExpense"], ""), "cogs": (["CostOfRevenue", "CostOfGoodsAndServicesSold"], ""),
        "sbc": (["ShareBasedCompensation"], ""),
    }
    H: dict[str, dict[int, dict[int, float]]] = {m: {} for m in hist}
    for y in yrs:
        log(f"SEC {y}")
        for m, (tags, suf, unit) in hist.items():
            H[m][y] = _merged(tags, f"CY{y}{suf}", unit)
    LT: dict[str, dict[int, float]] = {}
    for m, (tags, suf) in last.items():
        if suf == "Q4I":  # saldos: cierre de diciembre o, si cierra en otro mes, el trimestre más cercano
            LT[m] = {}
            for q in ("Q4I", "Q3I", "Q2I"):
                for c, v in _merged(tags, f"CY{Y}{q}").items():
                    LT[m].setdefault(c, v)
        else:
            LT[m] = _merged(tags, f"CY{Y}")
    by_cik: dict[int, dict] = {}
    for u in sec.universe():
        by_cik.setdefault(int(u["cik"]), u)

    rows = []
    for cik, u in by_cik.items():
        g = {m: [H[m][y].get(cik) for y in yrs] for m in hist}
        rev, ni, eps, sh, eq = g["rev"], g["ni"], g["eps"], g["sh"], g["eq"]
        if rev[-1] is None and ni[-1] is None:
            continue
        for i in range(1, len(yrs)):  # splits
            f = _split(sh[i] / sh[i - 1] if (sh[i] and sh[i - 1]) else None)
            if f:
                for j in range(i):
                    sh[j] = sh[j] * f if sh[j] else sh[j]
                    eps[j] = eps[j] / f if eps[j] is not None else None
        L = {m: LT[m].get(cik) for m in last}
        fcf = [(o - (c or 0)) if o is not None else None for o, c in zip(g["ocf"], g["capex"])]
        R, NI, OP, EQ = rev[-1], ni[-1], g["op"][-1], eq[-1]
        debt = (L["ltd"] or 0) + (L["std"] or 0)
        cash = L["cash"] or 0
        ebitda = (OP + (L["da"] or 0)) if OP is not None else None
        tax = min(max(_d(L["tax"], L["pretax"]) or 0.21, 0), 0.35) if L["pretax"] and L["pretax"] > 0 else 0.21
        ic = (debt + EQ - cash) if EQ is not None else None
        roes = [_d(n, e) for n, e in zip(ni[-5:], eq[-5:]) if e and e > 0 and n is not None]

        def downs(s):
            s = [x for x in s if x is not None]
            return sum(1 for a, b in zip(s, s[1:]) if b < a) if len(s) >= 3 else None

        rows.append({
            "Ticker": u["ticker"], "Empresa": u["name"], "Mercado": u["exchange"], "Año datos": Y,
            "_s_rev": rev, "_s_eps": eps, "BPA": eps[-1], "Acciones (M)": sh[-1] / 1e6 if sh[-1] else None,
            "_debt": debt, "_cash": cash, "_eq": EQ, "_fcf": fcf[-1], "_op": OP, "_ebitda": ebitda, "_div": L["div"], "_rev": R,
            "Ventas (M$)": R / 1e6 if R else None, "Beneficio (M$)": NI / 1e6 if NI is not None else None,
            "Crec. ventas 1a": (_d(R, rev[-2]) - 1) if (R and rev[-2]) else None,
            "CAGR ventas 3a": _cagr(R, rev[-4], 3), "CAGR ventas 5a": _cagr(R, rev[-6], 5),
            "Crec. BPA 1a": (_d(eps[-1], eps[-2]) - 1) if (eps[-1] is not None and eps[-2] and eps[-2] > 0) else None,
            "CAGR BPA 3a": _cagr(eps[-1], eps[-4], 3), "CAGR BPA 5a": _cagr(eps[-1], eps[-6], 5),
            "CAGR beneficio 5a": _cagr(NI, ni[-6], 5), "CAGR FCF 5a": _cagr(fcf[-1], fcf[-6], 5),
            "Años caída ventas": downs(rev[-6:]), "Años caída BPA": downs(eps[-6:]),
            "Años con pérdidas": sum(1 for x in ni[-6:] if x is not None and x < 0) if any(x is not None for x in ni[-6:]) else None,
            "Margen bruto": _d(L["gp"], R) if L["gp"] is not None else (_d(R - L["cogs"], R) if (R and L["cogs"] is not None) else None),
            "Margen operativo": _d(OP, R), "Margen neto": _d(NI, R), "Margen FCF": _d(fcf[-1], R),
            "I+D / ventas": _d(L["rnd"], R), "SBC / ventas": _d(L["sbc"], R),
            "ROE": _d(NI, EQ) if EQ and EQ > 0 else None, "ROE medio 5a": sum(roes) / len(roes) if len(roes) >= 3 else None,
            "ROA": _d(NI, L["assets"]), "ROIC": _d(OP * (1 - tax), ic) if (OP is not None and ic and ic > 0) else None,
            "Deuda / patrimonio": _d(debt, EQ) if EQ and EQ > 0 else None,
            "Deuda neta / EBITDA": _d(debt - cash, ebitda) if ebitda and ebitda > 0 else None,
            "Liquidez corriente": _d(L["ac"], L["lc"]),
            "Var. acciones 5a": _cagr(sh[-1], sh[-6], 5),
            "Payout": _d(L["div"] or 0, NI) if NI and NI > 0 else None,
            "Recompras / FCF": _d(L["bb"] or 0, fcf[-1]) if fcf[-1] and fcf[-1] > 0 else None,
            "FCF / beneficio": _d(fcf[-1], NI) if NI and NI > 0 else None,
            "Capex / OCF": _d(g["capex"][-1] or 0, g["ocf"][-1]) if g["ocf"][-1] and g["ocf"][-1] > 0 else None,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- precios y sectores (Nasdaq)
def _num(x):
    try:
        return float(str(x).replace("$", "").replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def build_market() -> pd.DataFrame:
    """Precio, capitalización, sector e industria de todas las acciones de EE. UU. (screener público de Nasdaq)."""
    r = requests.get("https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25&offset=0&download=true",
                     headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=60)
    rows = r.json()["data"]["rows"]
    return pd.DataFrame([{"Ticker": x["symbol"].strip().replace("/", "-").replace("^", "-P"), "Precio": _num(x.get("lastsale")),
                          "_mcap": _num(x.get("marketCap")), "Sector": x.get("sector") or "—", "Industria": x.get("industry") or "—"}
                         for x in rows])


# ---------------------------------------------------------------- tabla final
def avg_growth(series, n: int):
    """Media de los últimos n crecimientos anuales (si la base de algún año es ≤ 0, no hay dato)."""
    if series is None or len(series) < n + 1:
        return None
    s = [None if (x is None or pd.isna(x)) else float(x) for x in list(series)[-(n + 1):]]
    if s[0] is None or s[-1] is None:
        return None
    pts = [(i, x) for i, x in enumerate(s) if x is not None]
    g = []
    for (i, a), (j, b) in zip(pts, pts[1:]):
        k = j - i
        if a <= 0 or (k > 1 and b <= 0):
            return None
        g += [(b / a) ** (1 / k) - 1] * k
    return sum(g) / len(g)


def combine(base: pd.DataFrame, mk: pd.DataFrame | None, years_avg: int = 5) -> pd.DataFrame:
    df = base.copy()
    for m, col in AVG_GROWTH.items():
        df[m] = df[col].map(lambda s: avg_growth(s, years_avg)) if col in df else None
    if mk is None or mk.empty:
        for c in ("Precio", "Sector", "Industria"):
            df[c] = None
        return df
    mk = mk.drop_duplicates("Ticker").set_index("Ticker")
    for c in ("Precio", "_mcap", "Sector", "Industria"):
        df[c] = df["Ticker"].map(mk[c]) if c in mk else None
    df["Sector"] = df["Sector"].fillna("—")
    df["Industria"] = df["Industria"].fillna("—")
    num = lambda s: pd.to_numeric(s, errors="coerce")  # noqa: E731
    pos = lambda s: num(s).where(lambda x: x > 0)  # noqa: E731
    mcap = num(df["_mcap"]).where(lambda s: s > 0).fillna(num(df["Precio"]) * num(df["Acciones (M)"]) * 1e6)
    ev = mcap + num(df["_debt"]).fillna(0) - num(df["_cash"]).fillna(0)
    df["Capitalización (M$)"] = mcap / 1e6
    df["Valor empresa (M$)"] = ev / 1e6
    df["PER"] = num(df["Precio"]) / pos(df["BPA"])
    df["PEG"] = df["PER"] / (pos(df["CAGR BPA 5a"]) * 100)
    df["P/Ventas"] = mcap / pos(df["_rev"])
    df["P/Valor contable"] = mcap / pos(df["_eq"])
    df["P/FCF"] = mcap / pos(df["_fcf"])
    df["EV/EBIT"] = ev / pos(df["_op"])
    df["EV/EBITDA"] = ev / pos(df["_ebitda"])
    df["Rent. FCF"] = num(df["_fcf"]) / mcap
    df["Rent. dividendo"] = num(df["_div"]).fillna(0) / mcap
    return df


def apply_filters(df: pd.DataFrame, filters: dict[str, tuple], text: str = "", sectors=None, markets=None) -> pd.DataFrame:
    m = pd.Series(True, index=df.index)
    if markets:
        m &= df["Mercado"].isin(markets)
    if sectors:
        m &= df["Sector"].isin(sectors)
    if text:
        t = text.strip().lower()
        m &= df["Ticker"].str.lower().str.contains(t, regex=False) | df["Empresa"].str.lower().str.contains(t, regex=False)
    for col, (lo, hi) in filters.items():
        if col not in df:
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        if lo is not None:
            m &= s >= lo
        if hi is not None:
            m &= s <= hi
        if lo is not None or hi is not None:
            m &= s.notna()
    return df[m]
