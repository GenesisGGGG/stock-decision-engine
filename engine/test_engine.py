#!/usr/bin/env python3
"""
Offline tests for engine.py - no network needed.

A fake yfinance feeds the engine synthetic companies with the right answers built
in (e.g. every historical P/E is exactly 25x on period share counts), then checks
properties a correct engine must have, plus two closed-form identities:
  - constant growth at TG with a flat margin -> DCF equals the Gordon formula
  - ROE equal to the cost of equity -> residual income value equals book value

Run: python3 test_engine.py
"""
import json
import os
import sys
import tempfile
import types

import pandas as pd

FAKE = {}


class _Ticker:
    def __init__(self, tk):
        self.d = FAKE[tk]

    @property
    def info(self):
        return dict(self.d["info"])

    def get_income_stmt(self, freq="yearly"):
        return self.d["inc_q" if freq == "quarterly" else "inc_a"]

    def get_cashflow(self, freq="yearly"):
        return self.d["cf_q" if freq == "quarterly" else "cf_a"]

    def get_balance_sheet(self, freq="yearly"):
        return self.d["bs_q" if freq == "quarterly" else "bs_a"]

    def history(self, period=None, interval=None, auto_adjust=True):
        return self.d["hist"]

    @property
    def splits(self):
        return self.d["splits"]

    @property
    def fast_info(self):
        return types.SimpleNamespace(last_price=self.d["last_price"])


sys.modules["yfinance"] = types.SimpleNamespace(Ticker=_Ticker)
os.environ.setdefault("VALUATION_OUT_DIR", tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine  # noqa: E402

FY = [pd.Timestamp(f"{y}-12-31") for y in (2025, 2024, 2023, 2022)]  # newest first
QS = [pd.Timestamp(s) for s in ("2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30")]
TZ = "America/New_York"
TRUE_PE = 25.0
RF = 0.043


def frame(rows, cols):
    return pd.DataFrame({c: {k: v[i] for k, v in rows.items()} for i, c in enumerate(cols)})


def company(rev=200e9, g=0.10, ni_m=0.30, ebitda_m=0.45, ocf_m=0.40, capex_m=0.10, sbc_m=0.03,
            interest=2e9, shares_now=7.5e9, buyback=0.02, debt=60e9, leases=15e9, cash=80e9,
            eq_ratio=0.5, beta=1.1, payout=0.25, pe=TRUE_PE, premium=1.0,
            split=None, gaap_hit=None, px_override=None, price_override=None, drop=(), fwd_eps=None):
    """rev = FY2025 revenue; earlier years shrink at g. On normalized income and
    period-end shares, every FY-end P/E is exactly `pe`."""
    revs = [rev / (1 + g) ** i for i in range(4)]
    sh = [shares_now * (1 + buyback) ** (i + 1) for i in range(4)]   # true FY-end shares, current split units
    norm = [ni_m * r for r in revs]
    gaap = list(norm)
    if gaap_hit:
        gaap[1] *= gaap_hit                                          # one-off GAAP loss in FY2024
    px = px_override or [pe * n / s for n, s in zip(norm, sh)]       # split-adjusted FY-end closes
    rep_sh = list(sh)                                                # as reported on the statements
    if split:
        sdate, ratio = split
        rep_sh = [s / ratio if d < sdate else s for s, d in zip(sh, FY)]

    q_rev = rev * (1 + g) ** 0.5 / 4
    q = lambda m: [m * q_rev] * 5
    ltm_norm = 4 * ni_m * q_rev
    price = price_override or premium * pe * ltm_norm / shares_now
    eq_now = eq_ratio * 4 * q_rev

    f = {
        "inc_a": frame({"TotalRevenue": revs, "NormalizedIncome": norm, "NetIncomeCommonStockholders": gaap,
                        "NormalizedEBITDA": [ebitda_m * r for r in revs], "EBITDA": [ebitda_m * r for r in revs],
                        "InterestExpense": [interest] * 4, "TaxProvision": [0.18 * n / 0.82 for n in norm],
                        "PretaxIncome": [n / 0.82 for n in norm], "DilutedAverageShares": rep_sh}, FY),
        "inc_q": frame({"TotalRevenue": q(1), "NormalizedIncome": q(ni_m), "NetIncomeCommonStockholders": q(ni_m),
                        "NormalizedEBITDA": q(ebitda_m), "EBITDA": q(ebitda_m),
                        "InterestExpense": [interest / 4] * 5,
                        "DilutedAverageShares": [shares_now * 1.005] * 5}, QS),
        "cf_a": frame({"OperatingCashFlow": [ocf_m * r for r in revs],
                       "CapitalExpenditure": [-capex_m * r for r in revs],
                       "StockBasedCompensation": [sbc_m * r for r in revs]}, FY),
        "cf_q": frame({"OperatingCashFlow": q(ocf_m), "CapitalExpenditure": q(-capex_m),
                       "StockBasedCompensation": q(sbc_m)}, QS),
        "bs_a": frame({"TotalDebt": [debt] * 4, "CapitalLeaseObligations": [leases] * 4,
                       "CashCashEquivalentsAndShortTermInvestments": [cash] * 4,
                       "CommonStockEquity": [eq_ratio * r for r in revs], "OrdinarySharesNumber": rep_sh}, FY),
        "bs_q": frame({"TotalDebt": [debt] * 5, "CapitalLeaseObligations": [leases] * 5,
                       "CashCashEquivalentsAndShortTermInvestments": [cash] * 5,
                       "CommonStockEquity": [eq_now, eq_now, eq_now, eq_now, eq_now / (1 + g)],
                       "OrdinarySharesNumber": [shares_now] * 5}, QS),
    }
    idx = pd.date_range("2016-10-01", "2026-10-01", freq="MS", tz=TZ)

    def bar(ts):
        if ts.year >= 2026:
            return price
        return px[3] if ts.year < 2022 else px[2025 - ts.year]

    f["hist"] = pd.DataFrame({"Close": [bar(t) for t in idx]}, index=idx)
    f["splits"] = (pd.Series([split[1]], index=[pd.Timestamp(split[0], tz=TZ)]) if split
                   else pd.Series(dtype=float))
    f["last_price"] = 4.3
    f["info"] = {"currentPrice": price, "sharesOutstanding": shares_now, "beta": beta,
                 "totalRevenue": 4 * q_rev, "operatingCashflow": 4 * ocf_m * q_rev, "totalDebt": debt,
                 "totalCash": cash, "trailingEps": ltm_norm / shares_now, "payoutRatio": payout,
                 "shortName": "Synthetic"}
    if fwd_eps is not None:
        f["info"]["forwardEps"] = fwd_eps
    for where, key in drop:
        if where == "info":
            f["info"].pop(key, None)
        else:
            f[where] = f[where].drop(index=key, errors="ignore")
    return f


COMP = {"archetype": "compounder", "g": 0.10, "g_bear": 0.06, "g_bull": 0.14}
CASES = {
    "CMPD": (COMP, company(fwd_eps=9.0)),
    "SPLT": (COMP, company(split=(pd.Timestamp("2024-06-10"), 4.0))),
    "ONEOFF": (COMP, company(gaap_hit=0.5)),
    "INSR": ({"archetype": "compounder", "g": 0.08, "g_bear": 0.04, "g_bull": 0.12,
              "cash_excess_frac": 0.0, "smooth_ocf": True},
             company(rev=400e9, g=0.08, ni_m=0.04, ebitda_m=0.07, ocf_m=0.06, capex_m=0.01, sbc_m=0.002,
                     interest=4e9, shares_now=0.9e9, debt=80e9, leases=5e9, cash=30e9, eq_ratio=0.25,
                     beta=0.62, pe=20)),
    "BANK": ({"archetype": "financial", "g": 0.15, "g_bear": 0.08, "g_bull": 0.22},
             company(rev=4e9, g=0.20, ni_m=0.15, ebitda_m=0.30, ocf_m=0.10, capex_m=0.02, sbc_m=0.05,
                     interest=1e9, shares_now=1.1e9, buyback=-0.05, debt=3e9, leases=0.1e9, cash=3e9,
                     eq_ratio=1.8, beta=1.9, payout=0.0, pe=15)),
    "BURN": ({"archetype": "preprofit", "g": 0.45, "g_bear": 0.20, "g_bull": 0.80},
             company(rev=5e6, g=1.0, ni_m=-100.0, ebitda_m=-90.0, ocf_m=-80.0, capex_m=5.0, sbc_m=10.0,
                     interest=0.0, shares_now=0.7e9, buyback=-0.25, debt=0.1e9, leases=0.05e9, cash=1.5e9,
                     eq_ratio=300.0, beta=3.0, payout=0.0, px_override=[8.0, 6.0, 5.0, 9.0],
                     price_override=10.0)),
    "NOEPS": (COMP, company(drop=(("inc_q", "NormalizedIncome"), ("inc_q", "NetIncomeCommonStockholders"),
                                  ("info", "trailingEps")))),
    # Cash-rich, low-multiple name: DCF far above the multiples, so trimming drops it -
    # the UNH failure mode where draft 1's scenarios went flat.
    "TRIMDCF": (COMP, company(ni_m=0.10, ebitda_m=0.15, ocf_m=0.55, capex_m=0.02, sbc_m=0.0,
                              pe=10, beta=0.5)),
}

FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
    return cond


def model(out, key):
    return next(m for m in out["models"] if m["key"] == key)

def main():
    for tk, (cfg, data) in CASES.items():
        FAKE[tk] = data
        engine.CONFIG[tk] = cfg
    FAKE["^TNX"] = {"last_price": 4.3}

    outs = {}
    for tk, (cfg, _) in CASES.items():
        try:
            out = engine.evaluate(tk, RF)
        except Exception as e:
            check(False, f"{tk}: evaluate raised {type(e).__name__}: {e}")
            continue
        outs[tk] = out
        json.dumps(out, allow_nan=False)            # strict JSON or this raises
        m = out["master"]

        # Generic invariants
        if m["fv"] is not None:
            ws = sum(x["weight"] for x in out["models"])
            check(abs(ws - 1) < 1e-3, f"{tk}: blend weights sum to {ws}")
            survivors = [x["fv"] for x in out["models"] if x["weight"] > 0]
            check(min(survivors) - 0.01 <= m["fv"] <= max(survivors) + 0.01, f"{tk}: master outside survivors")
            bear, bull = out["scenarios"]["bear"]["master_fv"], out["scenarios"]["bull"]["master_fv"]
            if bear and bull:
                check(bear <= m["fv"] <= bull, f"{tk}: scenario ordering {bear} / {m['fv']} / {bull}")
        valid = [x["fv"] for x in out["models"] if x["valid"] and x["raw_weight"] > 0]
        if len(valid) >= 3:
            med = engine.median(valid)
            for x in out["models"]:
                if x["trimmed"]:
                    check(not (med / 2 <= x["fv"] <= med * 2), f"{tk}: {x['key']} trimmed but inside band")
                elif x["weight"] > 0:
                    check(med / 2 - 0.01 <= x["fv"] <= med * 2 + 0.01, f"{tk}: {x['key']} outside band, not trimmed")
        if len(valid) >= 2:
            check(m["dispersion"] is not None and abs(m["dispersion"]["ratio"] - max(valid) / min(valid)) < 0.01,
                  f"{tk}: dispersion does not cover every valid model")
        check(model(out, "revdcf")["weight"] == 0, f"{tk}: reverse DCF carries weight")
        mkt_row = next((x for x in out["models"] if x["key"] == "dcf_mkt"), None)
        if model(out, "revdcf")["implied_g"] is not None:
            check(mkt_row is not None and abs(mkt_row["fv"] / out["price"] - 1) < 0.01,
                  f"{tk}: dcf_mkt row missing or off price: "
                  + (f"{mkt_row['fv']} vs {out['price']}" if mkt_row else "row absent"))
            check(mkt_row["weight"] == 0 and mkt_row["role"] == "diagnostic",
                  f"{tk}: dcf_mkt must be a weightless diagnostic")
        else:
            check(mkt_row is None, f"{tk}: dcf_mkt row present but g* not computable")

        # Growth explorer curve: present for operating companies, monotonic, honest markers
        cur = out.get("dcf_curve")
        if tk == "BANK" or tk == "BURN":
            check(cur is None, f"{tk}: dcf_curve must be absent (gated)")
        elif cur:
            fvs = [p["fv"] for p in cur["points"]]
            check(all(b > a for a, b in zip(fvs, fvs[1:])), f"{tk}: curve not increasing in g")
            ga = cur["markers"].get("assumed")
            if ga is not None:
                near = min(cur["points"], key=lambda p: abs(p["g"] - ga))
                dcf_row = model(out, "dcf")
                if dcf_row["fv"]:
                    check(abs(near["fv"] / dcf_row["fv"] - 1) < 0.02,
                          f"{tk}: curve at assumed g disagrees with DCF model row")
            gm = cur["markers"].get("market")
            if gm is not None:
                near = min(cur["points"], key=lambda p: abs(p["g"] - gm))
                check(abs(near["fv"] / out["price"] - 1) < 0.02,
                      f"{tk}: curve at market g* should sit on the price")
                check("analyst_1y_fwd" in cur["markers"], f"{tk}: analyst marker missing")

        # Reverse DCF really solves DCF(g*) = price
        if model(out, "revdcf")["implied_g"] is not None:
            d = engine.load(tk, cfg)
            g_star, _ = engine.implied_growth(d, RF, d["beta"], cfg["g"])
            fv, _ = engine.dcf_value(d, g_star, RF, d["beta"])
            check(abs(fv / d["price"] - 1) < 1e-6, f"{tk}: DCF(g*) = {fv:.2f} vs price {d['price']:.2f}")

    if len(outs) < len(CASES):          # a crash already recorded - report it, skip dependent checks
        print("\n".join(["FAILED"] + ["  - " + f for f in FAILS]))
        sys.exit(1)

    # 12M price target: forward EPS x multiple; CMPD's synthetic trailing P/E is exactly 25
    t12 = outs["CMPD"]["target_12m"]
    check(t12["fv_revert"] is not None and abs(t12["fv_revert"] - 9.0 * TRUE_PE) < 0.5,
          f"CMPD: 12M revert target {t12['fv_revert']}, expected 9.0 x {TRUE_PE}")
    # hold vs revert differ by the share-count basis: LTM EPS uses the latest diluted
    # quarterly count, the historical median uses per-FY counts (0.5% apart by design)
    check(t12["fv_hold"] is not None and abs(t12["fv_hold"] / t12["fv_revert"] - 1) < 0.01,
          "CMPD: hold/revert ratio should equal pe_current/pe_median (share-basis gap only)")
    check(outs["BURN"]["target_12m"]["fv_revert"] is None,
          "BURN: 12M target must be withheld on negative forward EPS")

    # Historical P/E uses period share counts (buybacks), split heuristic, normalized basis
    for tk in ("CMPD", "SPLT", "ONEOFF"):
        d = engine.load(tk, CASES[tk][0])
        pe = d["mult"]["pe"]["median"]
        check(abs(pe - TRUE_PE) < 1e-6, f"{tk}: historical P/E {pe:.4f}, expected {TRUE_PE}")
    check(engine.load("ONEOFF", COMP)["basis"] == "normalized", "ONEOFF: not on normalized basis")

    # FCFF and the debt bridge on known numbers
    c = outs["CMPD"]["inputs"]
    q_rev = 200e9 * 1.1 ** 0.5 / 4
    expected = 4 * q_rev * (0.40 - 0.10 - 0.03) + 2e9 * (1 - 0.18)
    check(abs(c["fcff_ltm"] / expected - 1) < 1e-9, f"CMPD: FCFF {c['fcff_ltm']:.4g} vs {expected:.4g}")
    check(abs(c["debt_used"] - 45e9) < 1, f"CMPD: debt ex leases {c['debt_used']}")
    check(abs(c["beta_adj"] - (0.67 * 1.1 + 0.33)) < 1e-9, "CMPD: beta not Blume-adjusted")

    # Closed form 1: growth = TG throughout, flat margin -> Gordon growth
    d = engine.load("CMPD", COMP)
    d["fcfm_norm"] = None
    fv, _ = engine.dcf_value(d, engine.TG, RF, d["beta"])
    w, _ = engine.wacc(d, RF, d["beta"])
    ev = fv * d["shares"] + d["debt"] - d["cash_excess"]
    gordon = d["rev_ltm"] * (1 + engine.TG) * d["fcfm0"] / (w - engine.TG)
    check(abs(ev / gordon - 1) < 1e-9, f"DCF vs Gordon: {ev:.6g} vs {gordon:.6g}")

    # Closed form 2: ROE = cost of equity -> value = book
    _, ce = engine.wacc(d, RF, d["beta"])
    d["roe"] = ce
    fv, ok, _ = engine.ri_value(d, ce)
    check(abs(fv / d["bvps"] - 1) < 1e-9, f"RI at ROE=COE: {fv:.4f} vs book {d['bvps']:.4f}")

    # Closed form 3: residual income == dividends + terminal book (clean surplus)
    d = engine.load("CMPD", COMP)
    _, ce = engine.wacc(d, RF, d["beta"])
    d["roe"], d["payout"] = 0.30, 0.40
    fv, _, _ = engine.ri_value(d, ce)
    b, ddm, N = d["bvps"], 0.0, engine.RI_FADE_YEARS
    for t in range(1, N + 1):
        roe_t = 0.30 + (ce - 0.30) * (t - 1) / (N - 1)
        ddm += 0.40 * roe_t * b / (1 + ce) ** t
        b *= 1 + roe_t * 0.60
    ddm += b / (1 + ce) ** N
    check(abs(fv / ddm - 1) < 1e-9, f"RI vs DDM + terminal book: {fv:.4f} vs {ddm:.4f}")

    # Trimming that removes the DCF must not flatten the scenarios
    t = outs["TRIMDCF"]
    check("dcf" in t["master"]["trimmed_models"], f"TRIMDCF: setup failed, trimmed={t['master']['trimmed_models']}")
    check(t["scenarios"]["bear"]["master_fv"] < t["master"]["fv"] < t["scenarios"]["bull"]["master_fv"],
          "TRIMDCF: scenarios flat after trimming the DCF")

    # Archetype-specific behaviour
    i = outs["INSR"]
    check(i["inputs"]["cash_excess"] == 0, "INSR: regulated cash counted as excess")
    check(model(i, "dcf")["trimmed"] is False and model(i, "dcf")["weight"] > 0 or
          not model(i, "dcf")["valid"], "INSR: DCF dropped from blend")
    b = outs["BANK"]
    check(not model(b, "dcf")["valid"] and "bank" in model(b, "dcf")["note"], "BANK: DCF not gated")
    check(model(b, "pb")["valid"], "BANK: P/B not valid")
    check(b["master"]["fv"] is not None, "BANK: no master")
    br = outs["BURN"]
    check(br["master"]["fv"] is None and br["master"]["status"] == "no_valid_models",
          f"BURN: expected no master, got {br['master']}")
    check(br["diagnostics"].get("cash_runway_years", 0) > 0, "BURN: no runway diagnostic")
    n = outs["NOEPS"]
    check(not model(n, "pe")["valid"] and not model(n, "peg")["valid"], "NOEPS: P/E or PEG valid without EPS")
    check(n["master"]["fv"] is not None, "NOEPS: no master")
    for tk in ("CMPD", "INSR"):
        check(not any("flat" in w for w in outs[tk]["warnings"]), f"{tk}: flat scenarios")

    # Report
    print(f"{'ticker':7s}{'price':>9s}{'master':>9s}{'bear':>9s}{'bull':>9s}  status        trimmed")
    for tk, out in outs.items():
        m, s = out["master"], out["scenarios"]
        fmt = lambda x: f"{x:9.2f}" if x is not None else "      n/a"
        print(f"{tk:7s}{out['price']:9.2f}{fmt(m['fv'])}{fmt(s['bear']['master_fv'])}"
              f"{fmt(s['bull']['master_fv'])}  {m['status']:13s} {m['trimmed_models']}")
    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED")
        for f in FAILS:
            print("  -", f)
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
