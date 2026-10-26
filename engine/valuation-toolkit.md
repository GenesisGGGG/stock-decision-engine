# Valuation Toolkit — Screener Reference

Last updated: 2026-10-03

## Part 1: The 10 Models (original roster)

| Model | Overall | SoFi | UNH | NOC | ACHR | MSFT |
|---|---|---|---|---|---|---|
| DCF (FCFF) | 9 | 5 | 8.5 | 8.5 | 2 | 8 |
| DDM | 5 | 1 | 7 | 6.5 | 0 | 2.5 |
| Graham | 4 | 1 | 5.5 | 6 | 0 | 4 |
| Forward P/E | 8 | 4 | 8.5 | 8 | 0 | 8 |
| PEG | 7 | 4 | 8 | 5.5 | 0 | 7.5 |
| EV/EBITDA | 8.5 | 3 | 8 | 8.5 | 1 | 8 |
| P/S (EV/S) | 5 | 6.5 | 4.5 | 3.5 | 3 | 5.5 |
| P/B + Residual Income | 5.5 | 7.5 | 4 | 3 | 3 | 1.5 |
| Reverse DCF | 8.5 | 7 | 6.5 | 7 | 8 | 7.5 |
| Comps | 7 | 6 | 7 | 7.5 | 5 | 7 |

## Part 2: The Universal Blended Formula (selected roster: 7)

Every model outputs **fair value per share**. Multiples convert: target multiple × metric ÷ shares.

### Mechanical rules
1. **Validity gate**: undefined terms (negative EPS → P/E, PEG; negative EBITDA → EV/EBITDA; negative book → Res. Income) get weight forced to 0; surviving weights **renormalize to 1**.
2. **Target multiples from comps**: peer-group median (5yr or sector), not arbitrary.
3. **Dropped from blend**: DDM (redundant with DCF), Graham (fails on negative EPS), Comps as separate term (it calibrates the multiples).

### Formula
FV = w₁·DCF + w₂·RevDCF + w₃·(P/E target) + w₄·(PEG target) + w₅·(EV/EBITDA target) + w₆·(P/S target) + w₇·(Res. Income target); Σw = 1.

### Default universal prior
DCF 0.30 / RevDCF 0.20 / P/E 0.15 / PEG 0.05 / EV/EBITDA 0.15 / P/S 0.10 / RI 0.05

### Per-stock starting weights (backtest priors)
| Model | SoFi | UNH | NOC | ACHR | MSFT |
|---|---|---|---|---|---|
| DCF | 0.15 | 0.30 | 0.35 | 0.05 | 0.30 |
| RevDCF | 0.25 | 0.20 | 0.15 | 0.55 | 0.20 |
| P/E | 0.10 | 0.20 | 0.20 | 0 | 0.15 |
| PEG | 0 | 0.10 | 0 | 0 | 0.05 |
| EV/EBITDA | 0 | 0.15 | 0.20 | 0 | 0.15 |
| P/S | 0.20 | 0.05 | 0.05 | 0.30 | 0.10 |
| Res. Income | 0.30 | 0 | 0.05 | 0.10 | 0.05 |

### Roadmap (post-draft items, parked 2026-10-03)
1. **Outlier/fat-tail guardrails** — weighted mean breaks if one model goes rogue. Design: per-model output vs current price deviation bands (std range), flag any model >Nσ from ensemble, AI sanity layer on top to judge whether the outlier is wrong or the ensemble is.
2. **Weight optimization** — precise constants via backtest scripts against realized prices.
3. **Scenario distribution viz** — bear/base/bull inputs → run formula per case → bell curve / range chart of blended FV.
4. **Company similarity score (0-100)** — for comparing valuations among true competitors (threshold ~75+). Hard part: define "similar" (sector? margins? growth? business model? size?). Separate project, separate design pass.

### Draft-1 definition of done (~75% accurate)
- Runs on all 5 test tickers (SOFI, UNH, NOC, ACHR, MSFT) without crashing, valid output per archetype
- Each model emits (fv_per_share, valid, diagnostics); blender gates + renormalizes
- Output table: per-model FV vs current price, blended bear/base/bull, active models listed
- Target multiples = stock's own 5-yr median (peer DB deferred to draft 2)

### Backtest TODOs
- Optimize weights per stock against realized prices (bear/base/bull growth scenarios).
- Try **trimmed blend**: drop highest & lowest model outputs before weighting (expect ~10-15% accuracy gain).
- Reverse DCF anchor pulls FV toward price — track how much deviation each stock's blend actually produces.
