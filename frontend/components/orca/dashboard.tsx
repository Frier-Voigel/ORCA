"use client"

import { AlertCircle, X } from "lucide-react"
import { useState } from "react"
import { useOrcaState } from "@/hooks/use-orca-state"
import { applyStrategy, injectFault, resetSimulation, setControl } from "@/lib/orca/client"
import { FAULT_TYPES } from "@/lib/orca/constants"
import { ControlToolbar } from "./control-toolbar"
import { DependencyGraph } from "./dependency-graph"
import { LogFeed } from "./log-feed"
import { ProbabilityTimeline } from "./probability-timeline"
import { RcaCard } from "./rca-card"
import { StatusBar } from "./status-bar"
import { StrategyComparison } from "./strategy-comparison"

export function Dashboard() {
  const { data: state, error, mutate } = useOrcaState()
  const [service, setService] = useState("db-primary")
  const [fault, setFault] = useState<string>(FAULT_TYPES[1])
  const [speed, setSpeed] = useState(1)
  const [busy, setBusy] = useState(false)
  const [pendingKey, setPendingKey] = useState<string | null>(null)
  const [appliedKey, setAppliedKey] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const running = state?.running ?? true

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setActionError(null)
    try {
      await action()
      await mutate()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Request failed")
    } finally {
      setBusy(false)
    }
  }

  async function handleApply(strategy: string, target: string) {
    const key = `${strategy}:${target}`
    setPendingKey(key)
    await run(() => applyStrategy(strategy, target))
    setPendingKey(null)
    setAppliedKey(key)
    setTimeout(() => setAppliedKey((k) => (k === key ? null : k)), 2500)
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <StatusBar state={state} error={error} />
      <ControlToolbar
        service={service}
        fault={fault}
        running={running}
        speed={speed}
        busy={busy}
        onServiceChange={setService}
        onFaultChange={setFault}
        onInject={() => run(() => injectFault(service, fault))}
        onTogglePlay={() => run(() => setControl(running ? "pause" : "play", speed))}
        onSpeedChange={(s) => {
          setSpeed(s)
          run(() => setControl(running ? "play" : "pause", s))
        }}
        onReset={() => {
          setAppliedKey(null)
          run(resetSimulation)
        }}
      />

      {actionError || error ? (
        <div
          role="alert"
          className="mx-4 mt-4 flex items-center gap-2 rounded-md border border-failed/40 bg-failed/10 px-3 py-2 text-sm text-failed md:mx-6"
        >
          <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
          <p className="min-w-0 flex-1">
            {actionError ?? `Could not reach the Orca backend: ${error?.message}`}
          </p>
          {actionError ? (
            <button type="button" onClick={() => setActionError(null)} aria-label="Dismiss error">
              <X className="size-4" />
            </button>
          ) : null}
        </div>
      ) : null}

      <main className="grid flex-1 gap-4 p-4 md:p-6 lg:grid-cols-3">
        <div className="flex min-w-0 flex-col gap-4 lg:col-span-2">
          <DependencyGraph state={state} selected={service} onSelect={setService} />
          <ProbabilityTimeline state={state} />
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          <RcaCard state={state} />
          <LogFeed state={state} />
        </div>
        <div className="min-w-0 lg:col-span-3">
          <StrategyComparison
            state={state}
            pendingKey={pendingKey}
            appliedKey={appliedKey}
            onApply={handleApply}
          />
        </div>
      </main>
    </div>
  )
}
