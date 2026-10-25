"use client"

import { useEffect, useRef, useState } from "react"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { SERVICES } from "@/lib/orca/constants"
import { formatClock } from "@/lib/orca/status"
import type { LogLevel, SystemState } from "@/lib/orca/types"
import { cn } from "@/lib/utils"
import { Panel } from "./panel"

const LEVEL_STYLES: Record<LogLevel, string> = {
  ERROR: "bg-failed/15 text-failed border-failed/30",
  WARN: "bg-degraded/15 text-degraded border-degraded/30",
  INFO: "bg-primary/10 text-primary border-primary/25",
  DEBUG: "bg-muted text-muted-foreground border-border",
}

const ALL = "all"

export function LogFeed({ state }: { state?: SystemState }) {
  const [filter, setFilter] = useState<string>(ALL)
  const [autoScroll, setAutoScroll] = useState(true)
  const scrollRef = useRef<HTMLDivElement>(null)

  const logs = (state?.logs ?? []).filter((l) => filter === ALL || l.service === filter)
  const lastKey = logs.length ? `${logs.at(-1)!.ts}-${logs.length}` : ""

  useEffect(() => {
    if (!autoScroll || !scrollRef.current) return
    scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
  }, [lastKey, autoScroll])

  return (
    <Panel
      title="Log feed"
      description="Live structured logs"
      bodyClassName="p-0 flex flex-col"
      actions={
        <>
          <Select value={filter} onValueChange={(v) => setFilter((v as string) ?? ALL)}>
            <SelectTrigger size="sm" aria-label="Filter logs by service" className="w-36 font-mono text-xs">
              <SelectValue>{(v: string) => (v === ALL ? "All services" : v)}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL} className="text-xs">
                All services
              </SelectItem>
              {SERVICES.map((s) => (
                <SelectItem key={s} value={s} className="font-mono text-xs">
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Switch size="sm" checked={autoScroll} onCheckedChange={setAutoScroll} aria-label="Auto-scroll" />
            <span className="hidden sm:inline">Auto</span>
          </label>
        </>
      }
    >
      <div
        ref={scrollRef}
        className="h-80 overflow-y-auto px-2 py-2 font-mono text-xs lg:h-full lg:max-h-[420px]"
        role="log"
        aria-live="off"
        aria-label="Service logs"
      >
        {logs.length === 0 ? (
          <p className="p-4 text-center font-sans text-sm text-muted-foreground">No logs for this filter yet.</p>
        ) : (
          <ul className="flex flex-col">
            {logs.map((l, i) => (
              <li
                key={`${l.ts}-${l.service}-${i}`}
                className="grid grid-cols-[auto_auto_1fr] items-start gap-x-2 rounded px-2 py-1 hover:bg-muted/50"
              >
                <time className="text-muted-foreground tabular-nums">{formatClock(l.ts)}</time>
                <span
                  className={cn(
                    "w-12 rounded border px-1 text-center text-[10px] font-semibold leading-4",
                    LEVEL_STYLES[l.level],
                  )}
                >
                  {l.level}
                </span>
                <p className="min-w-0 break-words">
                  <button
                    type="button"
                    onClick={() => setFilter(l.service)}
                    className="mr-1.5 text-primary hover:underline"
                  >
                    {l.service}
                  </button>
                  <span className="text-foreground/85">{l.message}</span>
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Panel>
  )
}
