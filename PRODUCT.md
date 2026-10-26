# PRODUCT SPEC — Stock Decision Engine (working title)

## North Star
NOT a Yahoo Finance clone. A **decision engine**: boil the market down to the
minimum information needed to make an allocation decision. Data density is the
enemy. Every element must earn its pixels.

> "Boiling down the essentials to making decisions." — Nathan

## Hard constraints (from Nathan, 2026-10-02)
- **Everything fits in 1–2 scrolls.** No endless pages, no tab sprawl.
- **Aesthetics are non-negotiable.** "visually clean af." References he named:
  Finviz financials section (sales/earnings bar charts, GAAP EPS, clean tables).
- NOT 100-row data tables. **20–30 metrics max**, each with context:
  - vs market average
  - vs sector average
  - vs AI-selected peer group (similarity score ≥80 — his idea, BOOKMARKED as
    differentiating feature; peers recomputed per ticker, not GICS sector)
- **5–8 dials + 1 master dial.** (Simply Wall St snowflake is the genre
  reference; ours must look sharper and be formula-published.)
- **A few charts only.** Finviz-style small-multiple fundamentals charts.
- Valuation models + price-target algorithms + confidence scores (algos TBD
  together — physics brain wanted for the scoring math).
- Limited qualitative info (short thesis-style snippets, not news firehose).

## Layout v0 (for mockup, desktop 1440px)
Scroll 1 — The Decision:
  topbar (logo / ⌘K search / market status)
  ticker header: price + day change + sparkline | MASTER DIAL (composite
  score + verdict) | price-target range bar (low–high, marker at current)
  6-dial row: Valuation, Growth, Quality, Momentum, Sentiment, Risk
Scroll 2 — The Evidence:
  Finviz charts small-multiples: quarterly Sales bars, GAAP EPS bars,
  margin trend line
  Metric table (~24 rows): Metric | Value | vs Sector | vs AI Peers | percentile bar
  Peer chips: "AI peers (≥80): MSFT 92, AVGO 87, …" (teaser, later feature)
  News strip: 3–4 cards max

## Differentiators to build later (bookmarked)
1. AI peer grouping by similarity score (his idea — nobody free does this well)
2. Published scoring formulas (transparency as trust wedge vs black-box scores)
3. Confidence intervals on price targets, not point estimates
4. Chatbot navigator (Phase 4)

## Stack (decided 2026-10-02)
Next.js 14 App Router + Tailwind + shadcn/ui + Recharts. Blueprint repo:
DariusLukasukas/stocks (MIT). Data: Finnhub free (60 rpm quotes/news) +
FMP free (250/day fundamentals). Charts fallback: TradingView widgets.
Deploy: Vercel free under Nathan's GitHub (GenesisGGGG).

## Status
- [x] Blueprint cloned + running (Yahoo data blocked from our server IP — expected)
- [x] TradingView widget preview live (tunnel)
- [ ] GitHub device-verification code (emailed to n****@illinois.edu)
- [ ] Finnhub API key (Nathan signup)
- [ ] Static design mockup v0 ← IN PROGRESS
- [ ] Fork to own repo, rebrand, Finnhub data layer
- [ ] Vercel deploy under Nathan's name
