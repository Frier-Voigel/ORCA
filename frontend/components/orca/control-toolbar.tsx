"use client"

import { Pause, Play, RotateCcw, Zap } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { FAULT_TYPES, SERVICES, SPEEDS } from "@/lib/orca/constants"
import { cn } from "@/lib/utils"

interface ControlToolbarProps {
  service: string
  fault: string
  running: boolean
  speed: number
  busy: boolean
  onServiceChange: (v: string) => void
  onFaultChange: (v: string) => void
  onInject: () => void
  onTogglePlay: () => void
  onSpeedChange: (v: number) => void
  onReset: () => void
}

export function ControlToolbar(props: ControlToolbarProps) {
  const { service, fault, running, speed, busy } = props
  return (
    <div
      role="toolbar"
      aria-label="Simulation controls"
      className="flex flex-wrap items-center gap-3 border-b px-4 py-3 md:px-6"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-muted-foreground">Fault injector</span>
        <Select value={service} onValueChange={(v) => v && props.onServiceChange(v as string)}>
          <SelectTrigger aria-label="Target service" className="w-44 font-mono text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SERVICES.map((s) => (
              <SelectItem key={s} value={s} className="font-mono text-xs">
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={fault} onValueChange={(v) => v && props.onFaultChange(v as string)}>
          <SelectTrigger aria-label="Fault type" className="w-44 font-mono text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {FAULT_TYPES.map((f) => (
              <SelectItem key={f} value={f} className="font-mono text-xs">
                {f}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button onClick={props.onInject} disabled={busy} className="bg-failed text-white hover:bg-failed/85">
          <Zap aria-hidden="true" />
          Inject fault
        </Button>
      </div>

      <div className="hidden h-6 w-px bg-border md:block" aria-hidden="true" />

      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" onClick={props.onTogglePlay} disabled={busy} aria-pressed={running}>
          {running ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
          {running ? "Pause" : "Play"}
        </Button>

        <div role="radiogroup" aria-label="Simulation speed" className="flex items-center rounded-md border p-0.5">
          {SPEEDS.map((s) => (
            <button
              key={s}
              type="button"
              role="radio"
              aria-checked={speed === s}
              onClick={() => props.onSpeedChange(s)}
              disabled={busy}
              className={cn(
                "rounded px-2.5 py-1 font-mono text-xs transition-colors",
                speed === s ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {s}x
            </button>
          ))}
        </div>

        <Button variant="ghost" onClick={props.onReset} disabled={busy}>
          <RotateCcw aria-hidden="true" />
          Reset
        </Button>
      </div>
    </div>
  )
}
