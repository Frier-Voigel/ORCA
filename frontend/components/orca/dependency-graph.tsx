"use client"

import { NODE_POSITIONS } from "@/lib/orca/constants"
import { pct, STATUS_VAR } from "@/lib/orca/status"
import type { ServiceStatus, SystemState } from "@/lib/orca/types"
import { Panel } from "./panel"

const NODE_W = 128
const NODE_H = 46

function edgePoint(from: { x: number; y: number }, to: { x: number; y: number }, pad = 4) {
  const dx = to.x - from.x
  const dy = to.y - from.y
  const hw = NODE_W / 2 + pad
  const hh = NODE_H / 2 + pad
  const t = Math.min(dx === 0 ? Infinity : hw / Math.abs(dx), dy === 0 ? Infinity : hh / Math.abs(dy))
  return { x: from.x + dx * t, y: from.y + dy * t }
}

function segment(a: string, b: string) {
  const pa = NODE_POSITIONS[a]
  const pb = NODE_POSITIONS[b]
  if (!pa || !pb) return null
  return { start: edgePoint(pa, pb), end: edgePoint(pb, pa, 6) }
}

interface DependencyGraphProps {
  state?: SystemState
  selected: string
  onSelect: (service: string) => void
}

export function DependencyGraph({ state, selected, onSelect }: DependencyGraphProps) {
  const statusBy = new Map<string, ServiceStatus>(state?.metrics.map((m) => [m.service, m.status]) ?? [])
  const probBy = new Map(state?.predictions.predictions.map((p) => [p.service, p.fail_prob]) ?? [])
  const cascadeKeys = new Set(state?.cascade.paths.map((p) => `${p.to}->${p.from}`) ?? [])
  const origin = state?.incident.fault?.service
  const suspect = state?.root_cause.candidates[0]?.service
  const nodes = state?.graph.nodes ?? []
  const edges = state?.graph.edges ?? []
  const paths = state?.cascade.paths ?? []

  return (
    <Panel
      title="Dependency graph"
      description="12-service topology · arrows show predicted cascade direction"
      bodyClassName="p-2 md:p-3"
      actions={
        <ul className="hidden items-center gap-3 text-xs text-muted-foreground sm:flex" aria-label="Legend">
          {(["healthy", "degraded", "failed"] as const).map((s) => (
            <li key={s} className="flex items-center gap-1.5 capitalize">
              <span className="size-2 rounded-full" style={{ background: STATUS_VAR[s] }} aria-hidden="true" />
              {s}
            </li>
          ))}
          <li className="flex items-center gap-1.5">
            <svg width="18" height="6" aria-hidden="true">
              <line x1="0" y1="3" x2="18" y2="3" stroke="var(--failed)" strokeWidth="2" strokeDasharray="4 2" />
            </svg>
            cascade
          </li>
        </ul>
      }
    >
      <div className="w-full overflow-x-auto">
        <svg
          viewBox="0 0 1000 500"
          className="h-auto w-full min-w-[640px]"
          role="img"
          aria-label="Service dependency graph with failure status"
        >
          <defs>
            <marker id="arrow-cascade" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--failed)" />
            </marker>
            <marker id="arrow-dep" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="oklch(1 0 0 / 22%)" />
            </marker>
          </defs>

          <g>
            {edges.map((e) => {
              const seg = segment(e.source, e.target)
              if (!seg) return null
              const dimmed = cascadeKeys.has(`${e.source}->${e.target}`)
              return (
                <line
                  key={`${e.source}-${e.target}`}
                  x1={seg.start.x}
                  y1={seg.start.y}
                  x2={seg.end.x}
                  y2={seg.end.y}
                  stroke="oklch(1 0 0 / 16%)"
                  strokeWidth={1 + e.weight}
                  strokeDasharray={e.kind === "soft" ? "3 4" : undefined}
                  markerEnd="url(#arrow-dep)"
                  opacity={dimmed ? 0.3 : 1}
                />
              )
            })}
          </g>

          <g>
            {paths.map((p) => {
              const seg = segment(p.from, p.to)
              if (!seg) return null
              return (
                <g key={`c-${p.from}-${p.to}`}>
                  <line
                    x1={seg.start.x}
                    y1={seg.start.y}
                    x2={seg.end.x}
                    y2={seg.end.y}
                    stroke="var(--failed)"
                    strokeWidth={1.5 + p.prob * 2.5}
                    opacity={0.45 + p.prob * 0.55}
                    className="cascade-edge"
                    markerEnd="url(#arrow-cascade)"
                  >
                    <title>{`${p.from} → ${p.to}: ${pct(p.prob)} in ~${p.eta_s}s`}</title>
                  </line>
                </g>
              )
            })}
          </g>

          <g>
            {nodes.map((n) => {
              const pos = NODE_POSITIONS[n.id]
              if (!pos) return null
              const status = statusBy.get(n.id) ?? "healthy"
              const prob = probBy.get(n.id) ?? 0
              const color = STATUS_VAR[status]
              const isSelected = selected === n.id
              const x = pos.x - NODE_W / 2
              const y = pos.y - NODE_H / 2
              return (
                <g
                  key={n.id}
                  role="button"
                  tabIndex={0}
                  aria-label={`${n.id}, ${status}, failure probability ${pct(prob)}`}
                  aria-pressed={isSelected}
                  onClick={() => onSelect(n.id)}
                  onKeyDown={(ev) => {
                    if (ev.key === "Enter" || ev.key === " ") {
                      ev.preventDefault()
                      onSelect(n.id)
                    }
                  }}
                  className="cursor-pointer outline-none focus-visible:[&>rect.focus]:opacity-100"
                >
                  {status !== "healthy" ? (
                    <rect
                      x={x - 6}
                      y={y - 6}
                      width={NODE_W + 12}
                      height={NODE_H + 12}
                      rx={12}
                      fill={color}
                      className="node-pulse"
                    />
                  ) : null}
                  <rect
                    className="focus opacity-0"
                    x={x - 4}
                    y={y - 4}
                    width={NODE_W + 8}
                    height={NODE_H + 8}
                    rx={10}
                    fill="none"
                    stroke="var(--primary)"
                    strokeWidth={2}
                  />
                  <rect
                    x={x}
                    y={y}
                    width={NODE_W}
                    height={NODE_H}
                    rx={8}
                    fill="var(--card)"
                    stroke={isSelected ? "var(--primary)" : color}
                    strokeWidth={isSelected ? 2.5 : 1.5}
                    strokeDasharray={suspect === n.id && !isSelected ? "5 3" : undefined}
                    style={{ transition: "stroke 300ms" }}
                  />
                  <circle cx={x + 14} cy={pos.y - 7} r={4} fill={color} />
                  <text x={x + 24} y={pos.y - 3} fill="var(--foreground)" fontSize={13} fontFamily="var(--font-mono)">
                    {n.id}
                  </text>
                  <text x={x + 14} y={pos.y + 14} fill="var(--muted-foreground)" fontSize={11}>
                    {n.type}
                  </text>
                  <text
                    x={x + NODE_W - 10}
                    y={pos.y + 14}
                    textAnchor="end"
                    fill={color}
                    fontSize={12}
                    fontWeight={600}
                    fontFamily="var(--font-mono)"
                  >
                    {pct(prob)}
                  </text>
                  {origin === n.id ? (
                    <g>
                      <rect x={pos.x - 28} y={y - 18} width={56} height={15} rx={4} fill="var(--failed)" />
                      <text
                        x={pos.x}
                        y={y - 7}
                        textAnchor="middle"
                        fontSize={10}
                        fontWeight={700}
                        fill="white"
                        letterSpacing={0.5}
                      >
                        FAULT
                      </text>
                    </g>
                  ) : null}
                </g>
              )
            })}
          </g>
        </svg>
      </div>
    </Panel>
  )
}
