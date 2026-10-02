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
}

type Data = {
  ticker: string
  name: string
  price: number
  asof: string
  archetype: string
  g_base: number
  master: { fv: number | null; upside: number | null }
  models: Model[]
  scenarios?: Record<string, { master_fv: number | null }>
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

  useEffect(() => {
    setData(null)
    setErr(null)
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
      <style>{`
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
              Master Blend · 7-Model Weighted Formula
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 14, flexWrap: "wrap" }}>
              <div style={{ fontFamily: C.mono, fontSize: 40, fontWeight: 700, letterSpacing: "-.03em" }}>
                {fmt(data.master.fv)}
              </div>
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
            </div>

            <div style={{ marginTop: 18 }}>
              <PriceBar lo={lo} hi={hi} current={data.price} fv={data.master.fv} height={26} />
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, color: C.txt2, marginTop: 8 }}>
                <span>Low <b style={{ color: C.txt3 }}>—</b></span>
                <span>Current <b style={{ color: C.txt, fontFamily: C.mono }}>{fmt(data.price)}</b></span>
                <span>High <b style={{ color: C.txt3 }}>—</b></span>
              </div>
              <div style={{ fontSize: 12, color: C.txt3, marginTop: 6 }}>
                ● white = current price · <span style={{ color: C.green }}>◉ green = model value</span> ·
                {" "}{data.models.filter((m) => m.valid).length} of 7 models active (invalid gates → weight 0, renormalized) ·
                base growth {Math.round(data.g_base * 100)}% · {data.archetype} archetype
              </div>
            </div>
          </div>

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
                </div>
                {/* right: value + bar */}
                <div style={{ opacity: m.valid ? 1 : 0.38 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
                    <span style={{ fontFamily: C.mono, fontSize: 17, fontWeight: 700, color: m.valid ? C.txt : C.txt3 }}>
                      {m.valid ? fmt(m.fv) : "invalid"}
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
            Draft 1 · data as of {new Date(data.asof).toLocaleString()} · targets = 5yr median own multiples ·
            bear/bull scenarios computed, visualization pending · master blend gates invalid models and renormalizes weights.
          </div>
        </>
      )}
    </div>
  )
}
