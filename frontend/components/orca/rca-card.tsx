import { Crosshair, SearchCheck } from "lucide-react"
import { pct } from "@/lib/orca/status"
import type { SystemState } from "@/lib/orca/types"
import { Panel } from "./panel"

export function RcaCard({ state }: { state?: SystemState }) {
  const nominal = !state?.incident.active && (state?.system_health ?? 1) >= 0.95
  const candidates = nominal ? [] : (state?.root_cause.candidates ?? [])
  const [top, ...runnerUps] = candidates
  const blast = top ? (state?.cascade.blast_radius[top.service] ?? 0) : 0

  return (
    <Panel title="Root cause analysis" description="Ranked suspects with confidence">
      {!top ? (
        <div className="flex h-full min-h-40 flex-col items-center justify-center gap-2 text-center">
          <SearchCheck className="size-6 text-muted-foreground" aria-hidden="true" />
          <p className="text-sm text-muted-foreground">No anomalies detected. Inject a fault to start an investigation.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="rounded-md border border-failed/30 bg-failed/5 p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-failed">
                  <Crosshair className="size-3.5" aria-hidden="true" />
                  Top suspect
                </p>
                <p className="mt-1 truncate font-mono text-lg font-semibold">{top.service}</p>
              </div>
              <div className="text-right">
                <p className="font-mono text-2xl font-semibold tabular-nums text-failed">{pct(top.score)}</p>
                <p className="text-xs text-muted-foreground">confidence</p>
              </div>
            </div>
            <div
              className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted"
              role="meter"
              aria-label="Confidence"
              aria-valuenow={Math.round(top.score * 100)}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div className="h-full rounded-full bg-failed transition-[width] duration-500" style={{ width: pct(top.score) }} />
            </div>
            <p className="mt-3 text-pretty text-sm leading-relaxed text-foreground/90">{top.explanation}.</p>
            <p className="mt-2 text-xs text-muted-foreground">
              Blast radius: <span className="font-mono text-foreground">{blast}</span> downstream services
            </p>
          </div>

          {runnerUps.length > 0 ? (
            <div>
              <h3 className="mb-2 text-xs font-medium text-muted-foreground">Runner-ups</h3>
              <ul className="flex flex-col gap-2.5">
                {runnerUps.map((c) => (
                  <li key={c.service}>
                    <div className="flex items-center justify-between gap-2 text-sm">
                      <span className="truncate font-mono">{c.service}</span>
                      <span className="font-mono text-xs tabular-nums text-muted-foreground">{pct(c.score)}</span>
                    </div>
                    <div className="mt-1 h-1 overflow-hidden rounded-full bg-muted" aria-hidden="true">
                      <div className="h-full rounded-full bg-degraded/80" style={{ width: pct(c.score) }} />
                    </div>
                    <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{c.explanation}</p>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      )}
    </Panel>
  )
}
