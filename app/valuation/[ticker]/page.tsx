"use client"

import { useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import Link from "next/link"

type Model = {
  key: string
  name: string
  fv: number | null
  valid: boolean
  weight: number
  rating: number
  note: string
  role?: string
}

type Data = {
  ticker: string
  name: string
  price: number
  asof: string
  archetype: string
  g_base: number
  master: {
    fv: number | null
    upside: number | null
    status?: string
    coverage?: number
    dispersion: { min: number; max: number; ratio: number; level: string } | null
    trimmed_models: string[]
  }
  models: (Model & { trimmed?: boolean })[]
  scenarios?: Record<string, { master_fv: number | null; g_used?: number; beta_used?: number; moved_by?: string[] }>
  target_12m?: {
    eps_fwd: number | null
    pe_current: number | null
    pe_target: number | null
    pe_source: string | null
    fv_hold: number | null
    fv_revert: number | null
    upside_hold: number | null
    upside_revert: number | null
    note: string | null
  }
  diagnostics?: Record<string, number | string | null>
  warnings?: string[]
  dcf_curve?: {
    points: { g: number; fv: number }[]
    markers: Record<string, number | null>
  }
}

const TICKERS = ["MSFT", "UNH", "NOC", "SOFI", "ACHR", "AAPL"]

const C = {
  bg: "#090b0f",
  panel: "#10141b",
  border: "#1d2530",
  txt: "#e6e9ef",
  txt2: "#8b94a3",
  txt3: "#5b6472",
  green: "#34d399",
  red: "#f87171",
  amber: "#fbbf24",
  mono: "'JetBrains Mono', monospace",
}

const fmt = (n: number | null | undefined) =>
  n == null || !isFinite(n) ? "—" : "$" + n.toLocaleString(undefined, { maximumFractionDigits: 2 })

function ratingColor(r: number) {
  if (r >= 7) return C.green
  if (r >= 4) return C.amber
  return C.red
}

/** gradient bar, shared scale; white-ring dot = current price, filled dot = model FV */
function PriceBar({
  lo, hi, current, fv, height,
}: { lo: number; hi: number; current: number; fv: number | null; height: number }) {
  const span = hi - lo
  const pct = (v: number) => Math.min(98, Math.max(2, ((v - lo) / span) * 100))
  return (
    <div style={{ position: "relative", height, display: "flex", alignItems: "center" }}>
      <div
        style={{
          width: "100%",
          height: height * 0.45,
          borderRadius: 999,
          background: "linear-gradient(90deg,#f87171 0%,#fbbf24 45%,#34d399 100%)",
          opacity: 0.85,
        }}
      />
      {/* current price marker */}
      <div
        title={`Current ${fmt(current)}`}
        style={{
          position: "absolute",
          left: `${pct(current)}%`,
          top: "50%",
          transform: "translate(-50%,-50%)",
          width: 16,
          height: 16,
          borderRadius: "50%",
          background: "#fff",
          border: `3px solid ${C.bg}`,
          boxShadow: "0 0 0 2px #fff3",
          zIndex: 3,
        }}
      />
      {/* model FV marker */}
      {fv != null && fv > 0 && (
        <div
          title={`Model fair value ${fmt(fv)}`}
          style={{
            position: "absolute",
            left: `${pct(fv)}%`,
            top: "50%",
            transform: "translate(-50%,-50%)",
            width: 10,
            height: 10,
            borderRadius: "50%",
            background: "#0b0e13",
            border: `2.5px solid ${C.green}`,
            boxShadow: `0 0 8px ${C.green}66`,
            zIndex: 4,
          }}
        />
      )}
    </div>
  )
}

export default function ValuationPage() {
  const { ticker } = useParams<{ ticker: string }>()
  const router = useRouter()
  const [data, setData] = useState<Data | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [gPos, setGPos] = useState<number | null>(null)

  useEffect(() => {
    setData(null)
    setErr(null)
    setGPos(null)
    fetch(`/valuation/${ticker.toUpperCase()}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then(setData)
      .catch((e) => setErr(String(e)))
  }, [ticker])

  const up = (data?.master?.fv ?? 0) > data?.price!

  // shared scale across all 8 bars
  const validFvs = data?.models.filter((m) => m.valid && m.fv && m.fv > 0).map((m) => m.fv!) ?? []
  const all = data ? [data.price, ...validFvs] : [1]
  const lo = Math.min(...all) * 0.85
  const hi = Math.max(...all) * 1.15

  return (
    <div style={{ maxWidth: 1060, margin: "0 auto", padding: "28px 20px 60px", color: C.txt }}>
      <style suppressHydrationWarning>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&display=swap');
        .vchip { padding:5px 13px; border-radius:7px; border:1px solid ${C.border}; background:${C.panel};
                 font-family:${C.mono}; font-size:12px; font-weight:600; color:${C.txt2}; cursor:pointer; }
        .vchip:hover { border-color:#2c3947; color:${C.txt}; }
        .vchip.on { border-color:${C.green}; color:${C.green}; background:rgba(52,211,153,.08); }
        .mrow:hover { border-color:#2c3947 !important; }
      `}</style>

      {/* top bar */}
      <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap", marginBottom: 22 }}>
        <Link href="/mockup-v0.html" style={{ color: C.txt3, fontSize: 13, textDecoration: "none" }}>
          ← back
        </Link>
        <div style={{ fontSize: 16, fontWeight: 800, letterSpacing: "-.02em" }}>
          Model Breakdown <em style={{ color: C.green, fontStyle: "normal" }}>·</em>{" "}
          <span style={{ fontFamily: C.mono }}>{String(ticker).toUpperCase()}</span>
        </div>
        <div style={{ display: "flex", gap: 8, marginLeft: "auto", flexWrap: "wrap" }}>
          {TICKERS.map((t) => (
            <button key={t} className={`vchip ${t === String(ticker).toUpperCase() ? "on" : ""}`}
                    onClick={() => router.push(`/valuation/${t}`)}>
              {t}
            </button>
          ))}
        </div>
      </div>

      {err && <div style={{ color: C.red }}>failed to load {ticker}: {err}</div>}
      {!data && !err && <div style={{ color: C.txt3 }}>loading…</div>}

      {data && (
        <>
          {/* ── MASTER ── */}
          <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 16, padding: "24px 26px" }}>
            <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".09em", textTransform: "uppercase", color: C.txt3, marginBottom: 14 }}>
              Master Blend · 7 Models + 1 Diagnostic
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 14, flexWrap: "wrap" }}>
              <div style={{ fontFamily: C.mono, fontSize: 40, fontWeight: 700, letterSpacing: "-.03em" }}>
                {data.master.fv != null ? fmt(data.master.fv) : "n/a"}
              </div>
              {data.master.fv == null && (
                <div style={{ fontSize: 12.5, color: C.amber, fontFamily: C.mono }}>
                  master withheld · {data.master.status ?? "unknown"} (coverage {Math.round((data.master.coverage ?? 0) * 100)}% of model weight)
                </div>
              )}
              <div style={{ fontSize: 14, color: C.txt2 }}>
                blended fair value · current <b style={{ color: C.txt, fontFamily: C.mono }}>{fmt(data.price)}</b>
              </div>
              {data.master.upside != null && (
                <div style={{
                  marginLeft: "auto", fontFamily: C.mono, fontSize: 18, fontWeight: 700,
                  color: data.master.upside >= 0 ? C.green : C.red,
                }}>
                  {data.master.upside >= 0 ? "+" : ""}
                  {(data.master.upside * 100).toFixed(1)}%
                </div>
              )}
              <div style={{ marginTop: 14, display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                {data.master.dispersion && (
                  <span style={{
                    fontSize: 11.5, fontFamily: C.mono, fontWeight: 700, padding: "4px 10px", borderRadius: 6,
                    border: `1px solid ${data.master.dispersion.level === "HIGH" ? C.red : data.master.dispersion.level === "MODERATE" ? C.amber : C.green}`,
                    color: data.master.dispersion.level === "HIGH" ? C.red : data.master.dispersion.level === "MODERATE" ? C.amber : C.green,
                    background: data.master.dispersion.level === "HIGH" ? "rgba(248,113,113,.08)" : data.master.dispersion.level === "MODERATE" ? "rgba(251,191,36,.08)" : "rgba(52,211,153,.08)",
                  }}>
                    {data.master.dispersion.level} DISAGREEMENT · models span {fmt(data.master.dispersion.min)}–{fmt(data.master.dispersion.max)} ({data.master.dispersion.ratio.toFixed(1)}x)
                  </span>
                )}
                {data.master.trimmed_models?.length > 0 && (
                  <span style={{ fontSize: 11.5, color: C.txt3 }}>
                    outlier guard: dropped outside 0.5–2.0× median band ({data.master.trimmed_models.join(", ")})
                  </span>
                )}
              </div>
            </div>

            <div style={{ marginTop: 14 }}>
              <PriceBar lo={lo} hi={hi} current={data.price} fv={data.master.fv} height={26} />
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, color: C.txt2, marginTop: 8 }}>
                <span>Low <b style={{ color: C.txt3 }}>—</b></span>
                <span>Current <b style={{ color: C.txt, fontFamily: C.mono }}>{fmt(data.price)}</b></span>
                <span>High <b style={{ color: C.txt3 }}>—</b></span>
              </div>
              <div style={{ fontSize: 12, color: C.txt3, marginTop: 6 }}>
                ● white = current price · <span style={{ color: C.green }}>◉ green = model value</span> ·
                {" "}{data.models.filter((m) => m.valid).length} of {data.models.length} models active (invalid gates → weight 0, renormalized) ·
                base growth {Math.round(data.g_base * 100)}% · {data.archetype} archetype
              </div>
            </div>
          </div>

          {/* ── 12M PRICE TARGET ── */}
          {data.target_12m && (
            <div style={{ marginTop: 14, background: C.panel, border: `1px solid ${C.border}`, borderRadius: 16, padding: "18px 22px" }}>
              <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".09em", textTransform: "uppercase", color: C.txt3, marginBottom: 12 }}>
                12-Month Price Target · forward EPS × multiple
              </div>
              {data.target_12m.fv_revert != null ? (
                <div style={{ display: "flex", gap: 30, flexWrap: "wrap", alignItems: "baseline" }}>
                  <div>
                    <div style={{ fontSize: 11, color: C.txt3, fontFamily: C.mono }}>multiple holds ({data.target_12m.pe_current?.toFixed(1)}x)</div>
                    <div style={{ fontFamily: C.mono, fontSize: 26, fontWeight: 700 }}>{fmt(data.target_12m.fv_hold)}</div>
                    <div style={{ fontFamily: C.mono, fontSize: 12.5, fontWeight: 700, color: (data.target_12m.upside_hold ?? 0) >= 0 ? C.green : C.red }}>
                      {(data.target_12m.upside_hold ?? 0) >= 0 ? "▲" : "▼"} {Math.abs((data.target_12m.upside_hold ?? 0) * 100).toFixed(1)}%
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 11, color: C.txt3, fontFamily: C.mono }}>reverts to {data.target_12m.pe_target?.toFixed(1)}x ({data.target_12m.pe_source})</div>
                    <div style={{ fontFamily: C.mono, fontSize: 26, fontWeight: 700 }}>{fmt(data.target_12m.fv_revert)}</div>
                    <div style={{ fontFamily: C.mono, fontSize: 12.5, fontWeight: 700, color: (data.target_12m.upside_revert ?? 0) >= 0 ? C.green : C.red }}>
                      {(data.target_12m.upside_revert ?? 0) >= 0 ? "▲" : "▼"} {Math.abs((data.target_12m.upside_revert ?? 0) * 100).toFixed(1)}%
                    </div>
                  </div>
                  <div style={{ marginLeft: "auto", fontSize: 12, color: C.txt3, maxWidth: 380, lineHeight: 1.55 }}>
                    forward EPS <b style={{ color: C.txt, fontFamily: C.mono }}>${data.target_12m.eps_fwd?.toFixed(2)}</b> = analyst consensus (mechanical) ·
                    the <b style={{ color: C.txt }}>multiple is the dial</b> — override with{" "}
                    <code style={{ fontFamily: C.mono }}>target_pe</code> in CONFIG
                  </div>
                </div>
              ) : (
                <div style={{ fontSize: 12.5, color: C.amber, fontFamily: C.mono }}>unavailable · {data.target_12m.note}</div>
              )}
            </div>
          )}

          {/* ── GROWTH EXPLORER (slider over the precomputed DCF curve) ── */}
          {data.dcf_curve && (() => {
            const pts = data.dcf_curve!.points
            const mk = data.dcf_curve!.markers
            const lo = pts[0].g, hi = pts[pts.length - 1].g
            const pos = gPos ?? mk.market ?? data.g_base ?? lo
            const fvAt = (g: number): number => {
              if (g <= pts[0].g) return pts[0].fv
              for (let i = 0; i < pts.length - 1; i++) {
                if (g >= pts[i].g && g <= pts[i + 1].g) {
                  const t = (g - pts[i].g) / (pts[i + 1].g - pts[i].g || 1)
                  return pts[i].fv + (pts[i + 1].fv - pts[i].fv) * t
                }
              }
              return pts[pts.length - 1].fv
            }
            const fv = fvAt(pos), up = fv / data.price - 1
            const chips: [string, string, string][] = [
              ["assumed", "our g", C.txt],
              ["market", "market g*", "#60a5fa"],
              ["historical_5y", "5y hist", C.amber],
              ["analyst_1y_fwd", "analyst 1y", "#c084fc"],
            ]
            return (
              <div style={{ marginTop: 14, background: C.panel, border: `1px solid ${C.border}`, borderRadius: 16, padding: "18px 22px" }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 18, flexWrap: "wrap" }}>
                  <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".09em", textTransform: "uppercase", color: C.txt3 }}>
                    Growth → DCF
                  </div>
                  <div style={{ fontFamily: C.mono, fontSize: 22, fontWeight: 700 }}>{fmt(fv)}</div>
                  <div style={{ fontFamily: C.mono, fontSize: 13, fontWeight: 700, color: up >= 0 ? C.green : C.red }}>
                    {up >= 0 ? "▲" : "▼"} {Math.abs(up * 100).toFixed(1)}% vs price
                  </div>
                  <div style={{ marginLeft: "auto", fontFamily: C.mono, fontSize: 13, color: C.txt2 }}>
                    g = {(pos * 100).toFixed(1)}%
                  </div>
                </div>
                <input
                  type="range"
                  min={lo}
                  max={hi}
                  step={(hi - lo) / 200}
                  value={pos}
                  onChange={(e) => setGPos(parseFloat(e.target.value))}
                  style={{ width: "100%", marginTop: 12, accentColor: C.green }}
                />
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
                  {chips.map(([k, label, col]) => {
                    const v = mk[k]
                    if (v == null) return null
                    const on = Math.abs(pos - v) < (hi - lo) / 200
                    return (
                      <button
                        key={k}
                        onClick={() => setGPos(v)}
                        title={`jump to ${label}`}
                        style={{
                          fontSize: 11, fontFamily: C.mono, fontWeight: 700, padding: "4px 10px", borderRadius: 6,
                          border: `1px solid ${on ? col : C.border}`, color: col, cursor: "pointer",
                          background: on ? "rgba(255,255,255,.05)" : "transparent",
                        }}
                      >
                        {label} {(v * 100).toFixed(1)}%
                      </button>
                    )
                  })}
                </div>
              </div>
            )
          })()}

          {/* ── SCENARIOS + DIAGNOSTICS ── */}
          {data.scenarios && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10, marginTop: 14 }}>
              {(["bear", "base", "bull"] as const).map((sc) => {
                const v = sc === "base" ? { master_fv: data.master.fv, g_used: data.g_base }
                                          : data.scenarios?.[sc]
                const lab = sc === "base" ? "BASE" : sc.toUpperCase()
                const col = sc === "bear" ? C.red : sc === "bull" ? C.green : C.txt
                return (
                  <div key={sc} style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 10, padding: "10px 14px" }}>
                    <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: ".08em", color: C.txt3 }}>{lab}</div>
                    <div style={{ fontFamily: C.mono, fontSize: 17, fontWeight: 700, color: col, marginTop: 2 }}>
                      {v?.master_fv != null ? fmt(v.master_fv) : "n/a"}
                    </div>
                    <div style={{ fontSize: 11, color: C.txt3, marginTop: 2, fontFamily: C.mono }}>
                      g {v?.g_used != null ? `${Math.round(v.g_used * 100)}%` : "—"}
                      {v?.beta_used != null && ` · β ${v.beta_used}`}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
          {data.diagnostics?.cash_runway_years != null && (
            <div style={{ marginTop: 12, padding: "10px 14px", borderRadius: 10, border: `1px solid ${C.amber}`,
                          color: C.amber, fontSize: 12.5, fontFamily: C.mono, background: "rgba(251,191,36,.07)" }}>
              cash runway ≈ {Number(data.diagnostics.cash_runway_years).toFixed(1)} years at current burn
            </div>
          )}
          {data.warnings && data.warnings.length > 0 && (
            <div style={{ marginTop: 10, fontSize: 11.5, color: C.txt3, lineHeight: 1.7 }}>
              {data.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
            </div>
          )}

          {/* ── 7 MODEL ROWS ── */}
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".09em", textTransform: "uppercase", color: C.txt3, margin: "26px 4px 12px" }}>
            Individual Models
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {data.models.map((m) => (
              <div key={m.key} className="mrow"
                   style={{
                     display: "grid", gridTemplateColumns: "230px 1fr", gap: 20, alignItems: "center",
                     background: C.panel, border: `1px solid ${C.border}`, borderRadius: 12,
                     padding: "14px 20px", transition: "border-color .15s",
                   }}>
                {/* left: name / weight / rating */}
                <div>
                  <div style={{ fontWeight: 700, fontSize: 14 }}>{m.name}</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 6, fontSize: 12 }}>
                    <span style={{ fontFamily: C.mono, color: m.valid ? C.txt2 : C.txt3 }}>
                      w = {(m.weight * 100).toFixed(0)}%
                    </span>
                    <span style={{ display: "flex", alignItems: "center", gap: 5, color: ratingColor(m.rating), fontFamily: C.mono, fontSize: 11.5 }}>
                      <span style={{
                        width: 34, height: 4, borderRadius: 2, display: "inline-block",
                        background: `linear-gradient(90deg, ${ratingColor(m.rating)} ${m.rating * 10}%, ${C.border} ${m.rating * 10}%)`,
                      }} />
                      {m.rating}/10
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: C.txt3, marginTop: 5, lineHeight: 1.45 }}>{m.note}</div>
                  {m.trimmed && (
                    <div style={{ marginTop: 5 }}>
                      <span style={{
                        fontSize: 10, fontFamily: C.mono, fontWeight: 700, letterSpacing: ".06em",
                        padding: "2px 8px", borderRadius: 4,
                        border: `1px solid ${C.amber}`, color: C.amber, background: "rgba(251,191,36,.08)",
                      }}>
                        TRIMMED — outlier, excluded from blend
                      </span>
                    </div>
                  )}
                </div>
                {/* right: value + bar */}
                <div style={{ opacity: m.valid ? (m.trimmed ? 0.6 : 1) : 0.38 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
                    <span style={{ fontFamily: C.mono, fontSize: 17, fontWeight: 700, color: m.valid ? C.txt : C.txt3 }}>
                      {m.role === "diagnostic" ? "diagnostic" : m.valid ? fmt(m.fv) : "invalid"}
                    </span>
                    {m.valid && m.fv && (
                      <span style={{
                        fontFamily: C.mono, fontSize: 12, fontWeight: 600,
                        color: m.fv >= data.price ? C.green : C.red,
                      }}>
                        {m.fv >= data.price ? "▲" : "▼"} {(Math.abs(m.fv / data.price - 1) * 100).toFixed(1)}%
                      </span>
                    )}
                  </div>
                  <PriceBar lo={lo} hi={hi} current={data.price} fv={m.valid ? m.fv : null} height={16} />
                </div>
              </div>
            ))}
          </div>

          <div style={{ marginTop: 26, fontSize: 12, color: C.txt3, lineHeight: 1.6 }}>
            Draft 2 · data as of {data.asof.slice(0, 10)} · targets = median of own historical multiples (3–5 FY, period share counts) ·
            invalid models gated (weight 0) · outliers trimmed outside a 0.5–2.0× median band · dispersion spans ALL valid models (pre-trim) ·
            reverse DCF is a diagnostic (market-implied growth, never blended) · every input, fallback and clamp logged in the JSON (inputs / warnings).
          </div>
        </>
      )}
    </div>
  )
}
