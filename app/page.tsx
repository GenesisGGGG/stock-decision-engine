import Link from "next/link"
import { Button } from "@/components/ui/button"

const VALUATION_TICKERS = ["AAPL", "MSFT", "UNH", "NOC", "SOFI", "ACHR"]

export default function Home() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 py-16">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">StockIQ</h1>
        <p className="mt-2 text-muted-foreground">
          Valuation decision engine — multi-model fair value, per-model
          transparency, bear/base/bull scenarios. The Yahoo-backed market
          dashboard (this page&apos;s original version) is offline from this
          host&apos;s IP; the valuation engine below is fully live.
        </p>
      </div>

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">Valuation engine</h2>
        <div className="flex flex-wrap gap-2">
          {VALUATION_TICKERS.map((t) => (
            <Button key={t} asChild variant="outline">
              <Link href={`/valuation/${t}`}>{t}</Link>
            </Button>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">Design mockups</h2>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline">
            <a href="/mockup-v0.html">Dashboard mockup v0</a>
          </Button>
          <Button asChild variant="outline">
            <a href="/tv-preview.html">TradingView preview</a>
          </Button>
        </div>
      </section>
    </div>
  )
}
