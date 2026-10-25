"use client"

import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import type { SystemState } from "@/lib/orca/types"
import { Panel } from "./panel"

const LINE_COLORS = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"]
const TOP_N = 5

export function ProbabilityTimeline({ state }: { state?: SystemState }) {
  const history = state?.history.fail_prob ?? {}
  const top = Object.entries(history)
    .map(([service, values]) => ({ service, latest: values.at(-1) ?? 0 }))
    .sort((a, b) => b.latest - a.latest)
    .slice(0, TOP_N)
    .map((t) => t.service)

  const length = Math.max(0, ...top.map((s) => history[s]?.length ?? 0))
  const tick = state?.tick ?? 0
  const data = Array.from({ length }, (_, i) => {
    const row: Record<string, number> = { t: tick - (length - 1 - i) }
    for (const s of top) {
      const arr = history[s] ?? []
      const offset = length - arr.length
      const v = arr[i - offset]
      if (v !== undefined) row[s] = Math.round(v * 1000) / 10
    }
    return row
  })

  return (
    <Panel title="Probability timeline" description={`Failure probability · top ${TOP_N} services`}>
      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
            <CartesianGrid stroke="oklch(1 0 0 / 6%)" vertical={false} />
            <XAxis
              dataKey="t"
              tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              minTickGap={24}
            />
            <YAxis
              domain={[0, 100]}
              ticks={[0, 25, 50, 75, 100]}
              tickFormatter={(v) => `${v}%`}
              tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
              tickLine={false}
              axisLine={false}
            />
            <ReferenceLine y={70} stroke="var(--failed)" strokeDasharray="4 4" strokeOpacity={0.5} />
            <Tooltip
              cursor={{ stroke: "oklch(1 0 0 / 20%)" }}
              contentStyle={{
                background: "var(--popover)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                fontSize: 12,
              }}
              labelStyle={{ color: "var(--muted-foreground)" }}
              labelFormatter={(l) => `Tick ${l}`}
              formatter={(v, name) => [`${v}%`, name]}
            />
            {top.map((s, i) => (
              <Line
                key={s}
                type="monotone"
                dataKey={s}
                stroke={LINE_COLORS[i]}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5" aria-label="Timeline series">
        {top.map((s, i) => (
          <li key={s} className="flex items-center gap-1.5 font-mono text-xs text-muted-foreground">
            <span className="h-0.5 w-3 rounded" style={{ background: LINE_COLORS[i] }} aria-hidden="true" />
            {s}
          </li>
        ))}
      </ul>
    </Panel>
  )
}
