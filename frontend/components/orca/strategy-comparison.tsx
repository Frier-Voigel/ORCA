"use client"

import { Check, ShieldCheck, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { humanize, SCORE_WEIGHTS } from "@/lib/orca/constants"
import { healthStatus, pct, STATUS_VAR } from "@/lib/orca/status"
import type { RecoveryOption, SystemState } from "@/lib/orca/types"
import { cn } from "@/lib/utils"
import { Panel } from "./panel"

function MetricBar({ label, value, display, invert }: { label: string; value: number; display: string; invert?: boolean }) {
  const goodness = invert ? 1 - value : value
  const color = goodness >= 0.66 ? "bg-healthy" : goodness >= 0.4 ? "bg-degraded" : "bg-failed"
  return (
    <div>
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono tabular-nums">{display}</span>
      </div>
      <div className="mt-1 h-1 overflow-hidden rounded-full bg-muted" aria-hidden="true">
        <div className={cn("h-full rounded-full", color)} style={{ width: pct(Math.max(0.04, value)) }} />
      </div>
    </div>
  )
}

function ProjectedHealth({ values }: { values: number[] }) {
  return (
    <div>
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">Projected health</span>
        <span className="font-mono tabular-nums">{pct(values.at(-1) ?? 0)}</span>
      </div>
      <div
        className="mt-1.5 flex h-14 items-end gap-1"
        role="img"
        aria-label={`Projected health: ${values.map((v) => pct(v)).join(", ")}`}
      >
        {values.map((v, i) => (
          <div
            key={i}
            className="flex-1 rounded-sm transition-[height] duration-500"
            style={{ height: pct(Math.max(0.06, v)), background: STATUS_VAR[healthStatus(v)], opacity: 0.45 + (i / values.length) * 0.55 }}
          />
        ))}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
        <span>now</span>
        <span>+{values.length - 1} steps</span>
      </div>
    </div>
  )
}

function StrategyCard({
  option,
  maxSaved,
  pending,
  applied,
  onApply,
}: {
  option: RecoveryOption
  maxSaved: number
  pending: boolean
  applied: boolean
  onApply: () => void
}) {
  return (
    <article
      className={cn(
        "flex min-w-0 flex-col gap-3 rounded-lg border bg-background/40 p-4",
        option.recommended && "border-primary/60 bg-primary/5",
      )}
    >
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {option.recommended ? (
            <span className="mb-1 inline-flex items-center gap-1 rounded bg-primary/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary">
              <Sparkles className="size-3" aria-hidden="true" />
              Recommended
            </span>
          ) : null}
          <h3 className="truncate text-sm font-semibold">{humanize(option.strategy)}</h3>
          <p className="truncate font-mono text-xs text-muted-foreground">→ {option.target}</p>
        </div>
        <div className="text-right">
          <p className={cn("font-mono text-xl font-semibold tabular-nums", option.recommended && "text-primary")}>
            {Math.round(option.score * 100)}
          </p>
          <p className="text-[10px] text-muted-foreground">score</p>
        </div>
      </header>

      <p className="line-clamp-2 min-h-8 text-xs leading-relaxed text-muted-foreground">{option.rationale}</p>

      <div className="flex flex-col gap-2">
        <MetricBar
          label="Services saved"
          value={maxSaved ? option.services_saved / maxSaved : 0}
          display={String(option.services_saved)}
        />
        <MetricBar
          label="Recovery time"
          value={Math.min(1, option.est_recovery_s / 180)}
          display={`${Math.round(option.est_recovery_s)}s`}
          invert
        />
        <MetricBar label="Cost" value={option.cost} display={pct(option.cost)} invert />
        <MetricBar label="Risk" value={option.risk} display={pct(option.risk)} invert />
      </div>

      <ProjectedHealth values={option.projected_health} />

      <Button
        onClick={onApply}
        disabled={pending}
        variant={option.recommended ? "default" : "outline"}
        className="mt-auto w-full"
      >
        {applied ? <Check aria-hidden="true" /> : <ShieldCheck aria-hidden="true" />}
        {pending ? "Applying…" : applied ? "Applied" : "Apply"}
      </Button>
    </article>
  )
}

interface StrategyComparisonProps {
  state?: SystemState
  pendingKey: string | null
  appliedKey: string | null
  onApply: (strategy: string, target: string) => void
}

export function StrategyComparison({ state, pendingKey, appliedKey, onApply }: StrategyComparisonProps) {
  const options = state?.recovery.options ?? []
  const maxSaved = Math.max(1, ...options.map((o) => o.services_saved))

  return (
    <Panel
      title="Strategy comparison"
      description="Automated recovery options ranked by weighted score"
      actions={
        <ul className="hidden flex-wrap items-center gap-1.5 lg:flex" aria-label="Scoring weights">
          {SCORE_WEIGHTS.map((w) => (
            <li key={w.key} className="rounded border px-1.5 py-0.5 text-[11px] text-muted-foreground">
              {w.label} <span className="font-mono text-foreground">{w.weight.toFixed(2)}</span>
            </li>
          ))}
        </ul>
      }
    >
      {options.length === 0 ? (
        <div className="flex min-h-32 items-center justify-center text-sm text-muted-foreground">
          All services nominal — no recovery actions needed.
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
          {options.map((o) => {
            const key = `${o.strategy}:${o.target}`
            return (
              <StrategyCard
                key={key}
                option={o}
                maxSaved={maxSaved}
                pending={pendingKey === key}
                applied={appliedKey === key}
                onApply={() => onApply(o.strategy, o.target)}
              />
            )
          })}
        </div>
      )}
    </Panel>
  )
}
