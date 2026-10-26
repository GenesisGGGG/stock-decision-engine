#!/usr/bin/env python3
"""
Valuation engine - draft 2

Seven blended models plus one diagnostic. Writes one JSON per ticker for the site.
  blended:    dcf, pe, peg, evebitda, ps, pb, ri
  diagnostic: revdcf (market-implied starting growth - reported, never blended)

Each blended model returns (fv_per_share, valid, note). The blender drops invalid
models, trims outputs far from the median, renormalizes weights, and withholds the
master value when too little of the archetype's weight is computable.

Every fallback taken and every clamp that binds is written to "warnings" in the
output. README_AUDIT.md section 8 lists the changes from draft 1.
"""
import datetime
import json
import math
import os
import sys

import pandas as pd
import yfinance as yf

OUT_DIR = os.environ.get(
    "VALUATION_OUT_DIR",
    "/root/.openclaw/workspace/projects/stocks-blueprint/public/valuation",
)

# ---------------------------------------------------------------------------
# Calibration constants - judgment, not data
# ---------------------------------------------------------------------------
ERP = 0.046                 # equity risk premium (implied US ERP ballpark)
TG = 0.025                  # terminal growth
YEARS = 10                  # explicit DCF horizon
FCF_FADE_YEARS = 5          # years for FCFF margin to reach its historical median
RI_FADE_YEARS = 10          # years for ROE to fade to the cost of equity
TARGET_PEG = 1.2            # fair PEG anchor
PEG_MIN_G = 0.08            # PEG gated below 8% EPS growth (1.2 x 5 = 6x P/E is not a valuation)
BLUME = (0.67, 0.33)        # adjusted beta = 0.67 * raw + 0.33
BETA_BOUNDS = (0.3, 2.0)
SCEN_BETA_SHIFT = 0.15
TRIM_BAND = 2.0             # trim outputs above 2x or below 0.5x the median valid output
MIN_COVERAGE = 0.35         # withhold master if valid models carry < 35% of archetype weight
MIN_HIST_POINTS = 3         # fiscal years required behind any historical median
PS_MIN_REVENUE = 100e6
EXCLUDE_LEASES_FROM_DEBT = True   # lease payments already sit in OCF - README 4.1
SBC_AS_COST = True          # stock comp deducted from FCFF
RF_FALLBACK = 0.043
RF_BOUNDS = (0.01, 0.15)
TAX_BOUNDS = (0.10, 0.28)
CD_BOUNDS = (0.02, 0.08)

# ---------------------------------------------------------------------------
# Per-ticker assumptions (analyst judgment)
#   g, g_bear, g_bull : starting revenue growth, fading linearly to TG by year 10
#   g_eps             : EPS growth for PEG; defaults to g - set it when margins should move
#   cash_excess_frac  : share of balance-sheet cash treated as excess (default 1.0)
#   smooth_ocf        : average LTM FCFF margin with the last two FY margins
# ---------------------------------------------------------------------------
CONFIG = {
    "MSFT": {"archetype": "compounder", "g": 0.13, "g_bear": 0.09, "g_bull": 0.17},
    "UNH":  {"archetype": "compounder", "g": 0.10, "g_bear": 0.06, "g_bull": 0.14,
             "cash_excess_frac": 0.0,   # insurer: consolidated cash is mostly regulated subsidiary capital
             "smooth_ocf": True},       # CMS payment timing moves billions between quarters
    "NOC":  {"archetype": "defense",    "g": 0.05, "g_bear": 0.02, "g_bull": 0.08},
    "SOFI": {"archetype": "financial",  "g": 0.22, "g_bear": 0.14, "g_bull": 0.30},
    "ACHR": {"archetype": "preprofit",  "g": 0.45, "g_bear": 0.20, "g_bull": 0.80},
    "AAPL": {"archetype": "compounder", "g": 0.12, "g_bear": 0.08, "g_bull": 0.16},
}

BLEND_KEYS = ["dcf", "pe", "peg", "evebitda", "ps", "pb", "ri"]

WEIGHTS = {
    "compounder": {"dcf": .40, "pe": .25, "peg": .10, "evebitda": .20, "ps": .05, "pb": .00, "ri": .00},
    "defense":    {"dcf": .40, "pe": .25, "peg": .00, "evebitda": .25, "ps": .05, "pb": .00, "ri": .05},
    "financial":  {"dcf": .00, "pe": .35, "peg": .00, "evebitda": .00, "ps": .00, "pb": .30, "ri": .35},
    "preprofit":  {"dcf": .25, "pe": .00, "peg": .00, "evebitda": .00, "ps": .60, "pb": .00, "ri": .15},
}

# Display only - not used in any calculation.
RATING = {
    "MSFT": {"dcf": 8, "revdcf": 7.5, "pe": 8, "peg": 7.5, "evebitda": 8, "ps": 5.5, "ri": 1.5},
    "UNH":  {"dcf": 8.5, "revdcf": 6.5, "pe": 8.5, "peg": 8, "evebitda": 8, "ps": 4.5, "ri": 4},
    "NOC":  {"dcf": 8.5, "revdcf": 7, "pe": 8, "peg": 5.5, "evebitda": 8.5, "ps": 3.5, "ri": 3},
    "SOFI": {"dcf": 5, "revdcf": 7, "pe": 4, "peg": 4, "evebitda": 3, "ps": 6.5, "ri": 7.5},
    "ACHR": {"dcf": 2, "revdcf": 8, "pe": 0, "peg": 0, "evebitda": 1, "ps": 3, "ri": 3},
    "AAPL": {"dcf": 8, "revdcf": 7, "pe": 8, "peg": 7, "evebitda": 8, "ps": 5, "ri": 2},
}

NAMES = {"dcf": "DCF (FCFF)", "revdcf": "Reverse DCF (diagnostic)", "dcf_mkt": "DCF @ market g", "pe": "P/E (trailing)",
         "peg": "PEG", "evebitda": "EV/EBITDA", "ps": "P/S", "pb": "P/B", "ri": "Residual Income"}

# Yahoo statement row names: pretty=False form first, pretty=True form as fallback
K_REV = ["TotalRevenue", "Total Revenue"]
K_NORM = ["NormalizedIncome", "Normalized Income"]
K_NI = ["NetIncomeCommonStockholders", "Net Income Common Stockholders", "NetIncome", "Net Income"]
K_EBITDA_OPTS = [["NormalizedEBITDA", "Normalized EBITDA"], ["EBITDA"]]
K_TAX = ["TaxProvision", "Tax Provision"]
K_PTI = ["PretaxIncome", "Pretax Income"]
K_INT = ["InterestExpense", "Interest Expense"]
K_DSH = ["DilutedAverageShares", "Diluted Average Shares"]
K_OCF = ["OperatingCashFlow", "Operating Cash Flow"]
K_CAPEX = ["CapitalExpenditure", "Capital Expenditure"]
K_SBC = ["StockBasedCompensation", "Stock Based Compensation"]
K_DEBT = ["TotalDebt", "Total Debt"]
K_LEASE = ["CapitalLeaseObligations", "Capital Lease Obligations"]
K_CASH = ["CashCashEquivalentsAndShortTermInvestments",
          "Cash Cash Equivalents And Short Term Investments",
          "CashAndCashEquivalents", "Cash And Cash Equivalents"]
K_EQ = ["CommonStockEquity", "Common Stock Equity", "StockholdersEquity", "Stockholders Equity"]
K_SHO = ["OrdinarySharesNumber", "Ordinary Shares Number"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def num(x):
    """float, or None for None / NaN / inf / non-numerics."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def median(xs, positive=True):
    vals = sorted(v for v in (num(x) for x in xs) if v is not None and (v > 0 or not positive))
    n = len(vals)
    if n == 0:
        return None
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2


def clamp(x, lo, hi, label=None, warn=None):
    y = min(max(x, lo), hi)
    if warn is not None and y != x:
        warn.append(f"{label} clamped {x:.4g} -> {y:.4g}")
    return y


def r2(x):
    x = num(x)
    return round(x, 2) if x is not None else None


def safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None


def row(df, keys):
    if df is None or getattr(df, "empty", True):
        return None
    for k in keys:
        if k in df.index:
            s = df.loc[k]
            return s.iloc[0] if isinstance(s, pd.DataFrame) else s
    return None


def naive(ts):
    ts = pd.Timestamp(ts)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return ts.normalize()


def by_date(s):
    """Series indexed by period end -> {naive Timestamp: float}, NaNs dropped."""
    out = {}
    if s is None:
        return out
    for k, v in s.items():
        v = num(v)
        if v is not None:
            out[naive(k)] = v
    return out


def match(dt, series, tol_days=15):
    """Value for period end dt; tolerates statements dated a few days apart."""
    if dt in series:
        return series[dt]
    near = [(abs((k - dt).days), v) for k, v in series.items() if abs((k - dt).days) <= tol_days]
    return min(near, key=lambda p: p[0])[1] if near else None


def ltm(df_q, keys):
    """Sum of the four most recent quarters - only if they are four consecutive quarters."""
    s = by_date(row(df_q, keys))
    recent = sorted(s.items(), reverse=True)[:4]
    if len(recent) < 4:
        return None
    if not 250 <= (recent[0][0] - recent[-1][0]).days <= 300:
        return None
    return sum(v for _, v in recent)


def latest(df, keys):
    s = by_date(row(df, keys))
    return s[max(s)] if s else None


def clean(x):
    """JSON-safe: numpy scalars to Python, NaN/inf to None."""
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if x is None or isinstance(x, (bool, str)):
        return x
    if hasattr(x, "item"):
        x = x.item()
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    return x


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def load(tk, cfg):
    warn = []
    t = yf.Ticker(tk)
    info = safe(lambda: t.info) or {}
    inc_a = safe(t.get_income_stmt, freq="yearly")
    inc_q = safe(t.get_income_stmt, freq="quarterly")
    cf_a = safe(t.get_cashflow, freq="yearly")
    cf_q = safe(t.get_cashflow, freq="quarterly")
    bs_a = safe(t.get_balance_sheet, freq="yearly")
    bs_q = safe(t.get_balance_sheet, freq="quarterly")
    hist = safe(t.history, period="10y", interval="1mo", auto_adjust=False)
    splits = safe(lambda: t.splits)

    price = num(info.get("currentPrice")) or num(info.get("regularMarketPrice"))
    if not price:
        raise ValueError("no price")

    # Shares: diluted where available. Candidates far from sharesOutstanding are
    # ignored (stale pre-split counts); up to 3x is allowed for multi-class names.
    so = num(info.get("sharesOutstanding"))
    cands = [so] if so else []
    for c in (num(info.get("impliedSharesOutstanding")), latest(inc_q, K_DSH)):
        if c and (not so or 0.8 * so <= c <= 3.0 * so):
            cands.append(c)
    if not cands:
        raise ValueError("no share count")
    shares = max(cands)

    # Revenue
    rev_ltm = ltm(inc_q, K_REV)
    if rev_ltm is None:
        rev_ltm = num(info.get("totalRevenue"))
        if rev_ltm is not None:
            warn.append("LTM revenue from info (quarterly statements incomplete)")

    # Earnings: normalized (ex-unusual items) when LTM and >=3 FY exist, else GAAP.
    # LTM and history always use the same basis.
    ni_ltm = ltm(inc_q, K_NI)
    if ni_ltm is None and num(info.get("trailingEps")) is not None:
        ni_ltm = num(info["trailingEps"]) * shares
        warn.append("LTM GAAP earnings from info.trailingEps x diluted shares")
    norm_ltm, norm_hist = ltm(inc_q, K_NORM), by_date(row(inc_a, K_NORM))
    if norm_ltm is not None and len(norm_hist) >= MIN_HIST_POINTS:
        basis, earn_ltm, earn_hist = "normalized", norm_ltm, norm_hist
    else:
        basis, earn_ltm, earn_hist = "gaap", ni_ltm, by_date(row(inc_a, K_NI))
        warn.append("earnings basis GAAP (normalized income unavailable) - one-off items flow into multiples")

    # EBITDA: same row for LTM and history
    ebitda_key, ebitda_hist, ebitda_ltm = None, {}, None
    for opt in K_EBITDA_OPTS:
        h = by_date(row(inc_a, opt))
        if len(h) >= MIN_HIST_POINTS:
            ebitda_key, ebitda_hist, ebitda_ltm = opt, h, ltm(inc_q, opt)
            break
    if ebitda_ltm is None and num(info.get("ebitda")) is not None:
        ebitda_ltm = num(info["ebitda"])
        warn.append("LTM EBITDA from info (definition may differ from history)")

    # Cash flow LTM - signs preserved; abs() only where the sign convention is known
    ocf_ltm = ltm(cf_q, K_OCF)
    if ocf_ltm is None:
        ocf_ltm = num(info.get("operatingCashflow"))
        if ocf_ltm is not None:
            warn.append("OCF from info (quarterly cash flow incomplete)")
        else:
            ocf_ltm = latest(cf_a, K_OCF)
            if ocf_ltm is not None:
                warn.append("OCF from latest FY (no LTM available)")
    capex_ltm = ltm(cf_q, K_CAPEX)
    if capex_ltm is None:
        capex_ltm = latest(cf_a, K_CAPEX)
        if capex_ltm is not None:
            warn.append("capex from latest FY (no LTM available)")
    capex_ltm = abs(capex_ltm) if capex_ltm is not None else None
    sbc_ltm = ltm(cf_q, K_SBC)
    if sbc_ltm is None:
        sbc_ltm = latest(cf_a, K_SBC)
    if sbc_ltm is None:
        sbc_ltm = 0.0
        if SBC_AS_COST:
            warn.append("stock comp unavailable - treated as 0")
    sbc_ltm = abs(sbc_ltm)
    int_ltm = ltm(inc_q, K_INT)
    if int_ltm is None:
        int_ltm = latest(inc_a, K_INT)
    int_ltm = abs(int_ltm) if int_ltm is not None else None

    # Effective tax: median of per-FY rates, both legs positive, aligned by date
    tax_s, pti_s = by_date(row(inc_a, K_TAX)), by_date(row(inc_a, K_PTI))
    rates = [tax_s[k] / pti_s[k] for k in tax_s
             if k in pti_s and pti_s[k] > 0 and tax_s[k] > 0]
    if rates:
        tax = clamp(median(rates), *TAX_BOUNDS, "effective tax", warn)
    else:
        tax = 0.21
        warn.append("effective tax unavailable - 21% statutory used")

    # Balance sheet (latest quarter)
    debt_gross = latest(bs_q, K_DEBT)
    if debt_gross is None:
        debt_gross = num(info.get("totalDebt")) or 0.0
        warn.append("debt from info.totalDebt (lease split unavailable)")
        leases = 0.0
    else:
        leases = latest(bs_q, K_LEASE) or 0.0
    debt = max(debt_gross - leases, 0.0) if EXCLUDE_LEASES_FROM_DEBT else debt_gross
    cash = latest(bs_q, K_CASH)
    if cash is None:
        cash = num(info.get("totalCash")) or 0.0
        warn.append("cash from info.totalCash")
    cfrac = cfg.get("cash_excess_frac", 1.0)
    cash_excess = cash * cfrac

    eq_series = sorted(by_date(row(bs_q, K_EQ)).items(), reverse=True)
    equity = eq_series[0][1] if eq_series else None
    roe = None
    if equity and ni_ltm is not None:
        avg_eq = (equity + eq_series[4][1]) / 2 if len(eq_series) > 4 else equity
        roe = ni_ltm / avg_eq if avg_eq > 0 else None
    if roe is None and num(info.get("returnOnEquity")) is not None:
        roe = num(info["returnOnEquity"])
        warn.append("ROE from info.returnOnEquity")
    bvps = equity / shares if equity else num(info.get("bookValue"))
    payout = clamp(num(info.get("payoutRatio")) or 0.0, 0.0, 1.0)

    # Beta: Blume-adjusted toward 1, then clamped
    beta_raw = num(info.get("beta"))
    if beta_raw is None:
        beta = 1.0
        warn.append("beta unavailable - 1.0 used")
    else:
        beta = clamp(BLUME[0] * beta_raw + BLUME[1], *BETA_BOUNDS, "adjusted beta", warn)

    # Cost of debt
    if int_ltm and debt > 0:
        cd = clamp(int_ltm / debt, *CD_BOUNDS, "cost of debt", warn)
    else:
        cd = 0.05
        if debt > 0:
            warn.append("interest expense unavailable - 5% cost of debt used")

    def fcff(ocf, capex, sbc, interest):
        # OCF is after interest under US GAAP: add it back after tax to get FCFF
        return ocf - capex - (sbc if SBC_AS_COST else 0.0) + interest * (1 - tax)

    fcff_ltm = (fcff(ocf_ltm, capex_ltm, sbc_ltm, int_ltm or 0.0)
                if ocf_ltm is not None and capex_ltm is not None else None)
    burn_ltm = ocf_ltm - capex_ltm if ocf_ltm is not None and capex_ltm is not None else None

    # ---- per fiscal year history -------------------------------------------
    closes = None
    if hist is not None and not hist.empty and "Close" in hist:
        closes = hist["Close"].dropna().copy()
        if getattr(closes.index, "tz", None) is not None:
            closes.index = closes.index.tz_localize(None)

    def price_at(dt):
        if closes is None:
            return None
        s = closes.loc[:dt]
        return num(s.iloc[-1]) if len(s) else None

    split_list = []
    if splits is not None and len(splits):
        for k, v in splits.items():
            if num(v) and v > 0:
                split_list.append((naive(k), float(v)))

    def split_factor_after(dt):
        f = 1.0
        for sd, ratio in split_list:
            if sd > dt:
                f *= ratio
        return f

    rev_h = by_date(row(inc_a, K_REV))
    ocf_h, capex_h, sbc_h = (by_date(row(cf_a, K)) for K in (K_OCF, K_CAPEX, K_SBC))
    int_h = by_date(row(inc_a, K_INT))
    debt_h, lease_h, cash_h, eq_h = (by_date(row(bs_a, K)) for K in (K_DEBT, K_LEASE, K_CASH, K_EQ))
    sho_h, dsh_h = by_date(row(bs_a, K_SHO)), by_date(row(inc_a, K_DSH))

    years, share_fallback, nd_fallback = [], 0, 0
    for dt in sorted(rev_h, reverse=True):
        px = price_at(dt)
        sh = match(dt, sho_h) or match(dt, dsh_h)
        if sh:
            # Prices are split-adjusted. Statement share counts may or may not be:
            # take whichever reading is closer to today's count.
            f = split_factor_after(dt)
            if f != 1.0 and abs(math.log(sh * f / shares)) < abs(math.log(sh / shares)):
                sh *= f
        else:
            sh = shares
            share_fallback += 1
        dg, ch = match(dt, debt_h), match(dt, cash_h)
        if dg is not None and ch is not None:
            ls = match(dt, lease_h) or 0.0
            net_debt = (max(dg - ls, 0.0) if EXCLUDE_LEASES_FROM_DEBT else dg) - ch * cfrac
        else:
            net_debt = debt - cash_excess
            nd_fallback += 1
        o, c, sb, it = match(dt, ocf_h), match(dt, capex_h), match(dt, sbc_h), match(dt, int_h)
        margin = None
        if o is not None and c is not None and rev_h[dt] > 0 and (sb is not None or not SBC_AS_COST):
            margin = fcff(o, abs(c), abs(sb or 0.0), abs(it or 0.0)) / rev_h[dt]
        years.append({"date": dt, "mcap": px * sh if px else None, "rev": rev_h[dt],
                      "earn": match(dt, earn_hist),
                      "ebitda": match(dt, ebitda_hist) if ebitda_key else None,
                      "net_debt": net_debt, "equity": match(dt, eq_h), "fcff_margin": margin})
    if share_fallback:
        warn.append(f"{share_fallback} FY used today's share count (period share count missing)")
    if nd_fallback:
        warn.append(f"{nd_fallback} FY used today's net debt (period balance sheet missing)")

    # FCFF margin: LTM start, fade to the median the company actually printed
    fcfm0 = fcff_ltm / rev_ltm if fcff_ltm is not None and rev_ltm else None
    fy_margins = [y["fcff_margin"] for y in years if y["fcff_margin"] is not None]
    if cfg.get("smooth_ocf") and fcfm0 is not None and len(fy_margins) >= 2:
        fcfm0 = (fcfm0 + fy_margins[0] + fy_margins[1]) / 3
    fcfm_norm = None
    if len(fy_margins) >= MIN_HIST_POINTS:
        mm = median(fy_margins[:4], positive=False)
        if mm is not None and mm > 0:
            fcfm_norm = clamp(mm, 0.0, 0.60, "normalized FCFF margin", warn)

    # Trailing revenue CAGR - sanity check on the hand-set g
    rh = sorted(rev_h.items())
    rev_cagr = None
    if len(rh) >= 2 and rh[0][1] > 0 and rh[-1][1] > 0:
        span = (rh[-1][0] - rh[0][0]).days / 365.25
        if span >= 1:
            rev_cagr = (rh[-1][1] / rh[0][1]) ** (1 / span) - 1

    d = {
        "name": info.get("shortName", tk), "price": price, "shares": shares,
        "rev_ltm": rev_ltm, "ebitda_ltm": ebitda_ltm, "ebitda_basis": (ebitda_key or ["info"])[0],
        "earn_ltm": earn_ltm, "basis": basis,
        "eps_ltm": earn_ltm / shares if earn_ltm is not None else None,
        "eps_fwd": num(info.get("forwardEps")),
        "ni_ltm": ni_ltm, "ocf_ltm": ocf_ltm, "capex_ltm": capex_ltm, "sbc_ltm": sbc_ltm,
        "int_ltm": int_ltm, "fcff_ltm": fcff_ltm, "burn_ltm": burn_ltm,
        "fcfm0": fcfm0, "fcfm_norm": fcfm_norm,
        "tax": tax, "cd": cd, "debt": debt, "debt_gross": debt_gross, "leases": leases,
        "cash": cash, "cash_excess": cash_excess,
        "equity": equity, "bvps": bvps, "roe": roe, "payout": payout,
        "beta_raw": beta_raw, "beta": beta,
        "years": years, "rev_cagr": rev_cagr, "warnings": warn,
    }
    d["mult"] = hist_multiples(d)
    return d


def hist_multiples(d):
    """Medians of per-FY multiples, each built from that year's market cap
    (split-adjusted price x period share count) and that year's net debt."""
    pe, ps, ev, pb = [], [], [], []
    for y in d["years"]:
        mc = y["mcap"]
        if not mc or mc <= 0:
            continue
        if y["earn"] and y["earn"] > 0:
            pe.append(mc / y["earn"])
        if y["rev"] and y["rev"] > 0:
            ps.append(mc / y["rev"])
        if y["equity"] and y["equity"] > 0:
            pb.append(mc / y["equity"])
        if y["ebitda"] and y["ebitda"] > 0:
            ev.append((mc + y["net_debt"]) / y["ebitda"])

    def pack(xs):
        m = median(xs)
        n = sum(1 for x in xs if x > 0)
        return {"median": m, "n": n} if m is not None and n >= MIN_HIST_POINTS else None

    return {"pe": pack(pe), "ps": pack(ps), "evebitda": pack(ev), "pb": pack(pb)}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
def wacc(d, rf, beta):
    ce = rf + beta * ERP
    mcap = d["price"] * d["shares"]
    debt = d["debt"]
    if mcap + debt <= 0:
        return ce, ce
    w = (mcap * ce + debt * d["cd"] * (1 - d["tax"])) / (mcap + debt)
    return max(w, rf + 0.01), ce


def dcf_value(d, g, rf, beta):
    rev0, f0, fn = d["rev_ltm"], d["fcfm0"], d["fcfm_norm"]
    if not rev0 or rev0 <= 0:
        return None, "no revenue - gate"
    if f0 is None or f0 <= 0:
        return None, "FCFF margin <= 0 - gate"
    w, _ = wacc(d, rf, beta)
    if w <= TG + 0.005:
        return None, "WACC <= terminal growth - gate"
    pv, rev, fcf = 0.0, rev0, 0.0
    for y in range(1, YEARS + 1):
        gy = g + (TG - g) * (y - 1) / (YEARS - 1)
        rev *= 1 + gy
        m = f0 + (fn - f0) * min(y, FCF_FADE_YEARS) / FCF_FADE_YEARS if fn else f0
        fcf = rev * m
        pv += fcf / (1 + w) ** y
    tv = fcf * (1 + TG) / (w - TG) / (1 + w) ** YEARS
    eq = pv + tv - d["debt"] + d["cash_excess"]
    note = f"g={g:.1%} fading to {TG:.1%}, WACC={w:.1%}, FCFF margin {f0:.1%}"
    if fn:
        note += f" -> {fn:.1%} (historical median) by y{FCF_FADE_YEARS}"
    return eq / d["shares"], note


def implied_growth(d, rf, beta, g_base):
    """Starting growth g* at which the DCF equals today's price. Diagnostic only."""
    price, lo, hi = d["price"], -0.30, 0.60
    f_lo, note = dcf_value(d, lo, rf, beta)
    if f_lo is None:
        return None, f"not computable ({note})"
    f_hi, _ = dcf_value(d, hi, rf, beta)
    if price <= f_lo:
        return None, f"price below the DCF even at {lo:.0%} starting growth - market prices distress"
    if price >= f_hi:
        return None, f"price above the DCF even at {hi:.0%} starting growth"
    for _ in range(60):
        mid = (lo + hi) / 2
        fv, _ = dcf_value(d, mid, rf, beta)
        if fv > price:
            hi = mid
        else:
            lo = mid
    g_star = (lo + hi) / 2
    return g_star, f"market implies starting growth g*={g_star:.1%} vs assumed g={g_base:.1%}"


def ri_value(d, ce):
    """Residual income with ROE fading linearly to the cost of equity over
    RI_FADE_YEARS; excess returns are zero thereafter."""
    bv, roe = d["bvps"], d["roe"]
    if not bv or bv <= 0:
        return None, False, "book value <= 0 - gate"
    if roe is None or roe <= 0:
        return None, False, "ROE <= 0 or missing - gate"
    keep = 1 - d["payout"]
    val, b = bv, bv
    for t in range(1, RI_FADE_YEARS + 1):
        roe_t = roe + (ce - roe) * (t - 1) / (RI_FADE_YEARS - 1)
        val += (roe_t - ce) * b / (1 + ce) ** t
        b *= 1 + roe_t * keep
    return val, val > 0, (f"ROE {roe:.1%} fades to COE {ce:.1%} over {RI_FADE_YEARS}y; "
                          f"BVPS {bv:.2f}, payout {d['payout']:.0%}")


def run_models(d, cfg, rf, beta, g, g_eps):
    res, m, basis, eps, sh = {}, d["mult"], d["basis"], d["eps_ltm"], d["shares"]
    arch = cfg["archetype"]
    w, ce = wacc(d, rf, beta)

    # DCF
    if arch == "financial":
        res["dcf"] = (None, False, "FCFF undefined for a bank (debt and cash are operating items) - gate")
    else:
        fv, note = dcf_value(d, g, rf, beta)
        res["dcf"] = (fv, fv is not None and fv > 0, note)

    # P/E (trailing)
    if eps is None or eps <= 0:
        res["pe"] = (None, False, f"{basis} EPS missing or <= 0 - gate")
    elif m["pe"] is None:
        res["pe"] = (None, False, f"fewer than {MIN_HIST_POINTS} FY of positive earnings history - gate")
    else:
        t = m["pe"]["median"]
        res["pe"] = (eps * t, True, f"{basis} LTM EPS {eps:.2f} x {t:.1f}x "
                                    f"(median trailing P/E, {m['pe']['n']} FY)")

    # PEG
    if eps is None or eps <= 0:
        res["peg"] = (None, False, f"{basis} EPS missing or <= 0 - gate")
    elif g_eps < PEG_MIN_G:
        res["peg"] = (None, False, f"EPS growth {g_eps:.1%} below {PEG_MIN_G:.0%} - PEG not meaningful - gate")
    else:
        fair = TARGET_PEG * g_eps * 100
        res["peg"] = (eps * fair, True, f"fair P/E = {TARGET_PEG} x {g_eps * 100:.0f} = {fair:.1f}x on {basis} EPS")

    # EV/EBITDA
    eb = d["ebitda_ltm"]
    if arch == "financial":
        res["evebitda"] = (None, False, "EV/EBITDA not meaningful for a bank - gate")
    elif not eb or eb <= 0:
        res["evebitda"] = (None, False, "LTM EBITDA <= 0 or missing - gate")
    elif m["evebitda"] is None:
        res["evebitda"] = (None, False, f"fewer than {MIN_HIST_POINTS} FY of EV/EBITDA history - gate")
    else:
        t = m["evebitda"]["median"]
        eq = t * eb - d["debt"] + d["cash_excess"]
        res["evebitda"] = (eq / sh, eq > 0, f"{t:.1f}x LTM EBITDA (median, {m['evebitda']['n']} FY, period net debt)")

    # P/S
    rev = d["rev_ltm"]
    if not rev or rev < PS_MIN_REVENUE:
        res["ps"] = (None, False, "pre-revenue (LTM revenue < $100M) - gate")
    elif m["ps"] is None or m["ps"]["median"] >= 200:
        res["ps"] = (None, False, "no usable P/S history or target >= 200x - gate")
    else:
        t = m["ps"]["median"]
        res["ps"] = (t * rev / sh, True, f"{t:.2f}x LTM revenue (median, {m['ps']['n']} FY)")

    # P/B
    bv = d["bvps"]
    if not bv or bv <= 0:
        res["pb"] = (None, False, "book value <= 0 - gate")
    elif m["pb"] is None:
        res["pb"] = (None, False, f"fewer than {MIN_HIST_POINTS} FY of P/B history - gate")
    else:
        t = m["pb"]["median"]
        res["pb"] = (t * bv, True, f"{t:.2f}x BVPS {bv:.2f} (median, {m['pb']['n']} FY)")

    # Residual income
    res["ri"] = ri_value(d, ce)
    return res, {"wacc": w, "ce": ce}


# ---------------------------------------------------------------------------
# Blend
# ---------------------------------------------------------------------------
def dispersion(vals):
    vals = [v for v in vals if v and v > 0]
    if len(vals) < 2:
        return None
    lo, hi = min(vals), max(vals)
    r = hi / lo
    return {"min": round(lo, 2), "max": round(hi, 2), "ratio": round(r, 2),
            "level": "LOW" if r < 1.8 else ("MODERATE" if r < 2.5 else "HIGH")}


def blend(res, weights):
    valid = {k: res[k][0] for k in BLEND_KEYS
             if weights[k] > 0 and res[k][1] and res[k][0] is not None and res[k][0] > 0}
    coverage = sum(weights[k] for k in valid)
    survivors, trimmed = dict(valid), []
    if len(valid) >= 3:
        med = median(valid.values())
        keep = {k: v for k, v in valid.items() if med / TRIM_BAND <= v <= med * TRIM_BAND}
        if len(keep) >= 2:
            trimmed = [k for k in valid if k not in keep]
            survivors = keep
    wsum = sum(weights[k] for k in survivors)
    master = sum(weights[k] * v for k, v in survivors.items()) / wsum if wsum > 0 else None
    status = "ok"
    if not valid:
        status, master = "no_valid_models", None
    elif coverage < MIN_COVERAGE:
        status, master = "low_coverage", None
    return {"master": master, "status": status, "coverage": coverage,
            "weights": {k: weights[k] / wsum for k in survivors} if master is not None else {},
            "valid": valid, "trimmed": trimmed,
            "dispersion_all": dispersion(valid.values()),
            "dispersion_blend": dispersion(survivors.values())}


def wavg(res, weights, keys):
    ws = sum(weights[k] for k in keys)
    return sum(weights[k] * res[k][0] for k in keys) / ws if ws > 0 else None


# ---------------------------------------------------------------------------
# Evaluate
# ---------------------------------------------------------------------------
def risk_free(warn):
    try:
        raw = float(yf.Ticker("^TNX").fast_info.last_price)
    except Exception as e:
        warn.append(f"risk-free fetch failed ({type(e).__name__}) - {RF_FALLBACK:.2%} used")
        return RF_FALLBACK
    if not math.isfinite(raw):
        warn.append(f"risk-free not finite - {RF_FALLBACK:.2%} used")
        return RF_FALLBACK
    if raw > 20:  # old CBOE convention quoted the 10y at 10x
        warn.append(f"^TNX quoted {raw:.2f} - treated as the 10x convention")
        raw /= 10
    return clamp(raw / 100, *RF_BOUNDS, "risk-free", warn)


def evaluate(tk, rf, rf_warn=()):
    cfg = CONFIG[tk]
    arch = cfg["archetype"]
    w = WEIGHTS[arch]
    d = load(tk, cfg)
    warn = list(rf_warn) + d["warnings"]
    g = cfg["g"]
    g_eps = cfg.get("g_eps", g)

    res, rates = run_models(d, cfg, rf, d["beta"], g, g_eps)
    b = blend(res, w)
    master = b["master"]

    if arch == "financial":
        g_star, g_note = None, "not computed for a bank"
    else:
        g_star, g_note = implied_growth(d, rf, d["beta"], g)

    # Scenarios: the same valid model set as base, untrimmed, so trimming can never
    # drop the growth-sensitive models. The % move of that blend is applied to master.
    scenarios, scen_raw = {}, {}
    for sc, shift in (("bear", SCEN_BETA_SHIFT), ("bull", -SCEN_BETA_SHIFT)):
        g_s = cfg[f"g_{sc}"]
        beta_s = clamp(d["beta"] + shift, *BETA_BOUNDS)
        res_s, _ = run_models(d, cfg, rf, beta_s, g_s, g_eps + (g_s - g))
        keys = [k for k in b["valid"] if res_s[k][1] and res_s[k][0] is not None and res_s[k][0] > 0]
        base_avg, scen_avg = wavg(res, w, keys), wavg(res_s, w, keys)
        fv_s = master * scen_avg / base_avg if master and base_avg and scen_avg else None
        moved = [k for k in keys if abs(res_s[k][0] / res[k][0] - 1) > 1e-9]
        scen_raw[sc] = fv_s
        scenarios[sc] = {"master_fv": r2(fv_s), "g_used": g_s, "beta_used": round(beta_s, 3),
                         "moved_by": moved}
        if master and not moved:
            warn.append(f"{sc} scenario flat - no valid model responds to growth or beta")
    if master and scen_raw["bear"] and scen_raw["bull"]:
        if not scen_raw["bear"] <= master <= scen_raw["bull"]:
            warn.append("scenario ordering violated (expected bear <= base <= bull)")

    rnd = lambda x, n=4: round(x, n) if x is not None else None
    diag = {"implied_g": rnd(g_star), "implied_g_note": g_note, "g_base": g,
            "trailing_rev_cagr": rnd(d["rev_cagr"])}
    if d["rev_cagr"] is not None and abs(g - d["rev_cagr"]) > 0.10:
        warn.append(f"assumed g {g:.0%} vs trailing revenue CAGR {d['rev_cagr']:.0%} - check the assumption")
    if d["burn_ltm"] is not None and d["burn_ltm"] < 0:
        diag["cash_runway_years"] = rnd(d["cash"] / -d["burn_ltm"], 2)

    # ── 12-month price target: forward EPS x a chosen multiple ──
    # eps_fwd (analyst consensus) is the mechanical input; the multiple is the one
    # judgment dial. fv_hold: today's trailing P/E rides forward EPS (pure EPS-growth
    # bet, no re-rating). fv_revert: multiple reverts to the target (default: median
    # trailing P/E; per-ticker override via target_pe in CONFIG).
    pe_hist = (d["mult"].get("pe") or {}).get("median")
    pe_cur = d["price"] / d["eps_ltm"] if d["eps_ltm"] and d["eps_ltm"] > 0 else None
    ov = cfg.get("target_pe")
    if isinstance(ov, (int, float)) and not isinstance(ov, bool) and ov > 0:
        pe_t, pe_src = float(ov), "override"
    elif pe_hist and pe_hist > 0:
        pe_t, pe_src = pe_hist, "median trailing"
    else:
        pe_t, pe_src = pe_cur, "current (no P/E history)"
    eps_fwd = d["eps_fwd"] if d["eps_fwd"] and d["eps_fwd"] > 0 else None
    t12 = {"eps_fwd": r2(eps_fwd), "pe_current": r2(pe_cur), "pe_target": r2(pe_t),
           "pe_source": pe_src if pe_t else None,
           "fv_hold": None, "fv_revert": None, "upside_hold": None, "upside_revert": None,
           "note": None}
    if eps_fwd and pe_t and pe_t > 0:
        if pe_cur and pe_cur > 0:
            t12["fv_hold"] = r2(eps_fwd * pe_cur)
            t12["upside_hold"] = r2(eps_fwd * pe_cur / d["price"] - 1)
        t12["fv_revert"] = r2(eps_fwd * pe_t)
        t12["upside_revert"] = r2(eps_fwd * pe_t / d["price"] - 1)
        t12["note"] = "hold = forward EPS x today's trailing P/E (EPS-growth bet only); " \
                      "revert = forward EPS x target multiple (adds a re-rating bet)"
    else:
        t12["note"] = "forward EPS unavailable or non-positive - no 12M target"

    # ── growth explorer curve: DCF value as a function of starting growth ──
    # Precomputed once so the page can interpolate a growth slider client-side.
    # Markers show where the reference growth rates sit: our assumed g, the market's
    # implied g*, trailing 5y revenue CAGR, and analyst next-year EPS growth.
    g_hist = d["rev_cagr"]
    g_analyst = (d["eps_fwd"] / d["eps_ltm"] - 1) if (d["eps_fwd"] and d["eps_ltm"] and d["eps_ltm"] > 0) else None
    curve = None
    if arch != "financial" and d["fcff_ltm"] and d["fcff_ltm"] > 0:
        refs = [x for x in (g_star, g_hist, g_analyst, g, cfg.get("g_bull"), cfg.get("g_bear")) if x is not None]
        lo = max(-0.10, min(refs) - 0.03)
        hi = min(0.60, max(refs) + 0.03)
        pts = []
        for i in range(31):
            gi = lo + (hi - lo) * i / 30
            fvi, _ = dcf_value(d, gi, rf, d["beta"])
            if fvi is not None and math.isfinite(fvi):
                pts.append({"g": round(gi, 4), "fv": r2(fvi)})
        if len(pts) >= 5:
            curve = {"points": pts,
                     "markers": {"assumed": rnd(g), "market": rnd(g_star),
                                 "historical_5y": rnd(g_hist), "analyst_1y_fwd": rnd(g_analyst)}}
    diag["analyst_eps_growth_1y"] = rnd(g_analyst)

    models = []
    for k in BLEND_KEYS:
        fv, valid, note = res[k]
        models.append({"key": k, "name": NAMES[k], "role": "blend", "fv": r2(fv),
                       "valid": bool(valid and fv is not None and fv > 0),
                       "weight": round(b["weights"].get(k, 0.0), 4), "raw_weight": w[k],
                       "rating": RATING.get(tk, {}).get(k), "note": note,
                       "trimmed": k in b["trimmed"]})
    models.insert(1, {"key": "revdcf", "name": NAMES["revdcf"], "role": "diagnostic", "fv": None,
                      "valid": False, "weight": 0.0, "raw_weight": 0.0,
                      "rating": RATING.get(tk, {}).get("revdcf"), "note": g_note,
                      "trimmed": False, "implied_g": rnd(g_star)})
    if g_star is not None:
        fv_mkt, _ = dcf_value(d, g_star, rf, d["beta"])
        models.insert(1, {"key": "dcf_mkt", "name": NAMES["dcf_mkt"], "role": "diagnostic",
                          "fv": r2(fv_mkt), "valid": True, "weight": 0.0, "raw_weight": 0.0,
                          "rating": RATING.get(tk, {}).get("dcf_mkt"),
                          "note": (f"same DCF run at the market-implied growth g*={g_star:.1%} - lands "
                                   f"on the price by construction; this row shows the market's "
                                   f"assumption, not ours"), "trimmed": False})

    out = {
        "ticker": tk, "name": d["name"], "price": d["price"], "currency": "$",
        "asof": datetime.datetime.now().isoformat(timespec="seconds"),
        "archetype": arch, "g_base": g,
        "master": {"fv": r2(master),
                   "upside": round(master / d["price"] - 1, 4) if master else None,
                   "status": b["status"], "coverage": round(b["coverage"], 3),
                   "dispersion": b["dispersion_all"],        # all valid models, before trimming
                   "dispersion_blend": b["dispersion_blend"],  # models actually blended
                   "trimmed_models": b["trimmed"]},
        "models": models,
        "scenarios": scenarios,
        "diagnostics": diag,
        "target_12m": t12,
        "dcf_curve": curve,
        "inputs": {
            "rf": rf, "erp": ERP, "beta_raw": d["beta_raw"], "beta_adj": d["beta"],
            "cost_of_equity": rates["ce"], "wacc": rates["wacc"], "tax": d["tax"],
            "cost_of_debt": d["cd"], "shares_diluted": d["shares"],
            "debt_gross": d["debt_gross"], "leases_excluded": d["leases"] if EXCLUDE_LEASES_FROM_DEBT else 0.0,
            "debt_used": d["debt"], "cash": d["cash"], "cash_excess": d["cash_excess"],
            "rev_ltm": d["rev_ltm"], "ebitda_ltm": d["ebitda_ltm"], "ebitda_basis": d["ebitda_basis"],
            "earnings_ltm": d["earn_ltm"], "earnings_basis": d["basis"], "eps_ltm": d["eps_ltm"],
            "ocf_ltm": d["ocf_ltm"], "capex_ltm": d["capex_ltm"], "sbc_ltm": d["sbc_ltm"],
            "interest_ltm": d["int_ltm"], "fcff_ltm": d["fcff_ltm"],
            "fcff_margin_start": d["fcfm0"], "fcff_margin_norm": d["fcfm_norm"],
            "roe": d["roe"], "bvps": d["bvps"], "payout": d["payout"],
            "hist_years": len(d["years"]),
            "hist_multiples": d["mult"],
        },
        "warnings": warn,
    }
    return clean(out)


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    tickers = sys.argv[1:] or list(CONFIG)
    rf_warn = []
    rf = risk_free(rf_warn)
    for tk in tickers:
        try:
            out = evaluate(tk, rf, rf_warn)
            with open(os.path.join(OUT_DIR, f"{tk}.json"), "w") as f:
                json.dump(out, f, indent=2, allow_nan=False)
            m = out["master"]
            fv = f"{m['fv']:8.2f}" if m["fv"] is not None else f"     n/a ({m['status']})"
            up = f"{m['upside']:+.1%}" if m["upside"] is not None else "n/a"
            print(f"{tk:5s} price={out['price']:8.2f} master={fv} upside={up} "
                  f"valid={sum(1 for x in out['models'] if x['valid'])} warnings={len(out['warnings'])}")
        except Exception as e:
            print(f"{tk:5s} ERROR {type(e).__name__}: {e}")
