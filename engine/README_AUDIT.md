# Valuation Engine - Audit Spec (draft 2)

Purpose: multi-model fair-value blender for US equities. Fetches data via yfinance,
runs 7 valuation models plus 1 diagnostic, gates invalid outputs, trims outliers,
and blends the survivors into a master fair value with bear/bull scenarios.
Scope: engine.py is the entire calculation layer. The Next.js page only renders
the JSON this script produces.

Run: `pip install yfinance pandas; python3 engine.py [TICKERS...]` (defaults to all in CONFIG).
Offline tests: `python3 test_engine.py` (no network; see section 9).

Do not use the draft-1 sample outputs (sample-output-UNH.json, the MSFT summary). They
contradict the draft-1 code: the UNH weights sum to 0.8, and the MSFT bull case sits
below the base case. Re-run and check the real JSON.

## 1. Data flow
yfinance (unofficial Yahoo scraper; Yahoo fundamentals are vendor-standardized, not raw SEC filings)
-> load(ticker): statements (annual + quarterly), balance sheets, monthly prices, splits
-> run_models() -> {model: (fv, valid, note)}
-> blend() -> master, weights, trimmed, coverage, dispersion
-> evaluate() -> scenarios, diagnostics, inputs (audit trail), warnings -> JSON per ticker

Every fallback taken and every clamp that binds is appended to `warnings` in the output.

## 2. Inputs
| Field | Primary | Fallback | Clamp |
|---|---|---|---|
| price | info currentPrice / regularMarketPrice | - (error) | - |
| shares | max(sharesOutstanding, impliedSharesOutstanding, latest-quarter DilutedAverageShares) | - | candidates outside 0.8-3.0x sharesOutstanding ignored |
| revenue LTM | sum of 4 consecutive quarters TotalRevenue | info totalRevenue | - |
| earnings LTM + history | NormalizedIncome (4q sum; annual rows) | GAAP NetIncomeCommonStockholders, same basis for both | - |
| EBITDA LTM + history | NormalizedEBITDA, else EBITDA - same row for both | info ebitda | - |
| OCF / capex / SBC LTM | 4q sums from quarterly cash flow (signed; abs on capex and SBC only) | info OCF -> latest FY | - |
| interest LTM | 4q sum InterestExpense | latest FY | cost of debt [2%, 8%], else 5% |
| tax | median per-FY TaxProvision/PretaxIncome, date-aligned, both > 0 | 21% | [10%, 28%] |
| debt | latest quarter TotalDebt minus CapitalLeaseObligations | info totalDebt | >= 0 |
| cash | latest quarter cash + short-term investments, x cash_excess_frac | info totalCash | - |
| equity, ROE | CommonStockEquity; ROE = LTM GAAP NI / avg(equity now, 4q ago) | info returnOnEquity / bookValue | - |
| beta | Blume-adjusted: 0.67 x Yahoo 5y monthly beta + 0.33 | 1.0 | [0.3, 2.0] |
| risk-free | ^TNX / 100 (values > 20 treated as the old 10x quote) | 4.3% | [1%, 15%] |
| historical prices | monthly Close, `auto_adjust=False` (split-adjusted, not dividend-adjusted) | - | - |
| historical shares | annual OrdinarySharesNumber -> DilutedAverageShares, split-checked | today's count (warned) | - |

## 3. Constants (judgment, not data)
ERP 4.6%; TG 2.5%; DCF horizon 10y; FCFF margin fade 5y; RI fade 10y; TARGET_PEG 1.2;
PEG_MIN_G 8%; Blume 0.67/0.33; scenario beta shift +/-0.15; TRIM_BAND 2x;
MIN_COVERAGE 35%; MIN_HIST_POINTS 3 FY; P/S minimum revenue $100M.
Switches: EXCLUDE_LEASES_FROM_DEBT, SBC_AS_COST (both on).

## 4. Models
4.1 DCF (FCFF). Gated for financials.
  FCFF = OCF - capex - SBC + interest x (1 - tax)   [US GAAP OCF is after interest paid]
  fcfm0 = FCFF_LTM / rev_LTM (smooth_ocf: mean of LTM and last 2 FY margins)
  fcfm_norm = median FCFF margin of the last 4 FY actually printed (>= 3 points, used only if > 0, cap 60%)
  y = 1..10: g_y = g + (TG - g)(y - 1)/9; margin fades fcfm0 -> fcfm_norm by y5
  EV = sum FCFF_y/(1+w)^y + FCFF_10(1+TG)/(w-TG)/(1+w)^10; equity = EV - debt + cash x cash_excess_frac
  WACC = (mcap x ce + debt x cd x (1 - tax))/(mcap + debt), floor rf + 1%; ce = rf + beta x ERP
  Leases: operating lease payments sit inside OCF, so lease liabilities are excluded from debt.
  Finance-lease-funded assets are absent from both capex and debt (see 6.2).
4.2 Reverse DCF: diagnostic only, never blended. Bisection (60 iterations) for starting growth g*
  with DCF(g*) = price on [-30%, +60%]; reported as `implied_g` next to the assumed g.
4.3 P/E (trailing): EPS_LTM x median per-FY (mcap / earnings). Gate EPS > 0, >= 3 FY.
4.4 PEG: EPS_LTM x 1.2 x g_eps x 100. g_eps defaults to g. Gate EPS > 0, g_eps >= 8%.
4.5 EV/EBITDA: (median per-FY (mcap + that year's net debt)/EBITDA x EBITDA_LTM - debt + cash_excess)/shares.
4.6 P/S: median per-FY mcap/revenue x rev_LTM / shares. Gate revenue >= $100M, target < 200x.
4.7 P/B: median per-FY mcap/equity x BVPS. Gate BVPS > 0, >= 3 FY.
4.8 Residual income: value = B0 + sum_{t=1..10} (ROE_t - ce) B_{t-1}/(1+ce)^t,
  ROE_t fades linearly from LTM ROE to ce, B_t = B_{t-1}(1 + ROE_t(1 - payout)), zero excess return after.
  Gate BVPS > 0, ROE > 0. Equals dividends + terminal book discounted (clean surplus; tested).
Per-FY market cap = split-adjusted FY-end close x that year's share count. A statement count that
predates a split is rescaled when that reading sits closer to today's count.

## 5. Blend
valid = model-valid, fv > 0, archetype weight > 0. coverage = sum of raw weights of valid models.
Trim: with >= 3 valid, drop any output outside [median/2, median x 2] (only if >= 2 remain).
master = weighted mean of survivors, weights renormalized to 1.
Withheld (fv null) when nothing is valid (`no_valid_models`) or coverage < 35% (`low_coverage`).
dispersion = max/min over all valid models (before trimming); dispersion_blend = survivors only.
LOW < 1.8, MODERATE < 2.5, else HIGH.
Scenarios: g -> g_bear/g_bull (g_eps shifted by the same delta), beta +/-0.15. The blend is recomputed
over the base's valid set, untrimmed, and its % move is applied to master. Trimming can no longer
remove the growth-sensitive models. A flat scenario or a bear > base > bull violation is warned.

Weights (draft 1's reverse-DCF weight redistributed):
| archetype | dcf | pe | peg | evebitda | ps | pb | ri |
|---|---|---|---|---|---|---|---|
| compounder | .40 | .25 | .10 | .20 | .05 | 0 | 0 |
| defense | .40 | .25 | 0 | .25 | .05 | 0 | .05 |
| financial | 0 | .35 | 0 | 0 | 0 | .30 | .35 |
| preprofit | .25 | 0 | 0 | 0 | .60 | 0 | .15 |
RATING is display-only and feeds no calculation.

## 6. Known approximations (disclosed)
1. FCFF margin normalization assumes reversion to the company's own recent median.
2. Finance-lease-funded capex is in neither capex nor debt (understates hyperscaler capex).
3. Historical multiples rest on 3-5 annual points; restatements rewrite history.
4. Normalized income is Yahoo's definition of "unusual items".
5. Beta is one 5y regression, shrunk toward 1 (Blume) - still regime-sensitive.
6. RI book growth uses dividend payout only; buybacks also shrink book.
7. Per-ticker g, g_bear, g_bull, g_eps, cash_excess_frac and smooth_ocf are analyst judgment.
   `warnings` flags any g more than 10pp from trailing revenue CAGR.
8. Yahoo is not an auditable source. For a verifiable pipeline, take fundamentals from SEC EDGAR
   XBRL (companyfacts API) and keep yfinance for prices.

## 7. Output schema (additions to draft 1)
master: status, coverage, dispersion (now all valid models), dispersion_blend.
models[]: role ("blend" | "diagnostic"); revdcf carries implied_g, never fv; new key "pb".
scenarios.{bear,bull}: g_used, moved_by (models that responded).
diagnostics: implied_g, trailing_rev_cagr, cash_runway_years (cash burners).
inputs: every number the models consumed. warnings: list of strings.
The page must handle master.fv = null.

## 8. Changes from draft 1
| Draft 1 | Draft 2 |
|---|---|
| Historical multiples on today's share count | Per-year share counts, split-checked |
| Capex ratios zipped by position after dropna | Every series aligned by date |
| P/E crashed on missing EPS; silent 18x fallback marked valid | Gated with reason |
| abs() on OCF fallback (cash burners looked profitable) | Signs preserved |
| info["capitalExpenditures"] (not a Yahoo field) | Cash-flow statements |
| OCF - capex discounted at WACC | FCFF: interest added back after tax, SBC deducted |
| Raw Yahoo beta | Blume-adjusted |
| Normalization: today's OCF margin minus old capex intensity | Median FCFF margin actually printed |
| Leases possibly inside debt | Excluded (payments already in OCF) |
| Basic shares | Diluted |
| Reverse DCF in blend as price x g/g* | Diagnostic only |
| RI: Gordon on TTM ROE forever | ROE fades to cost of equity |
| DCF and EV/EBITDA on banks | Gated; P/B added |
| PEG on revenue g, any g >= 3% | g_eps, gated below 8% |
| Min/max trim at >= 5 models | Median band, any count >= 3 |
| Dispersion after trimming | Before trimming (blend dispersion also reported) |
| Scenarios on trimmed survivors (flat for UNH) | Untrimmed valid set, % move applied |
| Master from any single valid model | Withheld below 35% coverage |
| "Forward P/E", "5y median" labels | "P/E (trailing)", actual FY count |
| GAAP history (one-offs distort) | Normalized income, same basis LTM and history |
| Dividend-adjusted prices | auto_adjust=False |
| Historical EV on today's net debt | That year's net debt |
| Silent clamps and fallbacks | Logged to warnings |
| NaN could reach JSON | Strict JSON (allow_nan=False) |

## 9. Tests (test_engine.py)
A fake yfinance serves synthetic companies with the right answers built in, then checks:
- every historical P/E equals the constructed 25x, through buybacks, a 4:1 split and a one-off GAAP loss
- FCFF, the lease-adjusted debt and the Blume beta match hand-computed values
- constant growth at TG reproduces the Gordon formula exactly
- ROE = cost of equity makes RI equal book; RI equals dividends + terminal book
- reverse DCF solves DCF(g*) = price
- weights sum to 1; master sits within the survivors; trims fall outside the band
- dispersion spans every valid model; bear <= base <= bull, including when trimming drops the DCF
- banks gate the DCF; a pre-revenue cash burner returns no master plus a runway; missing EPS gates P/E without crashing
Thirteen fixes (share counts, split check, FCFF interest, Blume beta, leases, scenarios, dispersion,
normalized basis, insurer cash, RI fade, bank gate, trimming, P/E crash) were each reverted
one at a time; the suite fails on every one.
