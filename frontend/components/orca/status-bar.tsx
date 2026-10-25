import { Activity, AlertTriangle, CheckCircle2, Radio, Waves } from "lucide-react"
import { API_LABEL, IS_LIVE } from "@/lib/orca/client"
import { healthStatus, STATUS_TEXT, STATUS_VAR, pct } from "@/lib/orca/status"
import type { SystemState } from "@/lib/orca/types"
import { cn } from "@/lib/utils"

function HealthGauge({ value }: { value: number }) {
  const status = healthStatus(value)
  const radius = 26
  const circumference = Math.PI * radius
  const offset = circumference * (1 - value)
  return (
    <div className="flex items-center gap-3">
      <svg viewBox="0 0 64 38" className="h-10 w-16" role="img" aria-label={`System health ${pct(value)}`}>
        <path
          d={`M 6 34 A ${radius} ${radius} 0 0 1 58 34`}
          fill="none"
          stroke="var(--muted)"
          strokeWidth="6"
          strokeLinecap="round"
        />
        <path
          d={`M 6 34 A ${radius} ${radius} 0 0 1 58 34`}
          fill="none"
          stroke={STATUS_VAR[status]}
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-[stroke-dashoffset] duration-500"
        />
      </svg>
      <div className="leading-tight">
        <p className="text-xs text-muted-foreground">System health</p>
        <p className={cn("font-mono text-lg font-semibold tabular-nums", STATUS_TEXT[status])}>{pct(value)}</p>
      </div>
    </div>
  )
}

export function StatusBar({ state, error }: { state?: SystemState; error?: Error }) {
  const incident = state?.incident
  const failing = state?.metrics.filter((m) => m.status !== "healthy").length ?? 0

  return (
    <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-b bg-card/60 px-4 py-3 backdrop-blur md:px-6">
      <div className="flex items-center gap-3">
        <div className="flex size-9 items-center justify-center rounded-md bg-primary/15 text-primary">
          <Waves className="size-5" aria-hidden="true" />
        </div>
        <div className="leading-tight">
          <h1 className="text-base font-semibold tracking-tight">Orca</h1>
          <p className="text-xs text-muted-foreground">Cascading failure predictor</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <HealthGauge value={state?.system_health ?? 1} />

        <div role="status" aria-live="polite">
          {incident?.active ? (
            <div className="flex items-center gap-2 rounded-md border border-failed/40 bg-failed/10 px-3 py-1.5 text-failed">
              <span className="relative flex size-2">
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-failed opacity-75" />
                <span className="relative inline-flex size-2 rounded-full bg-failed" />
              </span>
              <AlertTriangle className="size-4" aria-hidden="true" />
              <span className="text-sm font-medium">
                Incident active
                {incident.fault ? (
                  <span className="ml-1 font-mono text-xs opacity-80">
                    {incident.fault.service} · {incident.fault.type}
                  </span>
                ) : null}
              </span>
              <span className="rounded bg-failed/20 px-1.5 font-mono text-xs">{failing}</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 rounded-md border border-healthy/30 bg-healthy/10 px-3 py-1.5 text-healthy">
              <CheckCircle2 className="size-4" aria-hidden="true" />
              <span className="text-sm font-medium">No incidents</span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Activity className="size-4 text-muted-foreground" aria-hidden="true" />
          <div className="leading-tight">
            <p className="text-xs text-muted-foreground">Tick</p>
            <p className="font-mono text-sm font-semibold tabular-nums">{state?.tick ?? "—"}</p>
          </div>
        </div>

        <div
          className={cn(
            "flex items-center gap-2 rounded-md border px-2.5 py-1 text-xs",
            error ? "border-failed/40 text-failed" : "text-muted-foreground",
          )}
          title={API_LABEL}
        >
          <Radio className={cn("size-3.5", !error && state?.running && "text-healthy")} aria-hidden="true" />
          <span>{error ? "Backend unreachable" : IS_LIVE ? "Live API" : "Demo mode"}</span>
        </div>
      </div>
    </header>
  )
}
