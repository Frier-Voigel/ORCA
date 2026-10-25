import {
  FAULT_TYPES,
  GRAPH_EDGES,
  GRAPH_NODES,
  NODE_BASELINES,
  SCORE_WEIGHTS,
  SERVICES,
  STRATEGIES,
} from "./constants"
import type {
  CascadePath,
  LogLine,
  MetricTick,
  PredictionItem,
  RecoveryOption,
  RootCauseCandidate,
  ServiceStatus,
  SystemState,
} from "./types"

/**
 * In-browser stand-in for the FastAPI backend. Mirrors the /api/state contract so the
 * dashboard is fully usable in the preview when NEXT_PUBLIC_ORCA_API_URL is not set.
 */

type Fault = { service: string; type: string; tick: number }

const HISTORY_LEN = 30
const FAULT_RATE: Record<string, number> = {
  memory_leak: 0.06,
  slow_query: 0.12,
  network_partition: 0.22,
  bad_deploy: 0.15,
  cpu_spike: 0.1,
}

const EFFECTIVENESS: Record<string, Record<string, number>> = {
  restart: { memory_leak: 0.9, bad_deploy: 0.4, cpu_spike: 0.7, slow_query: 0.5, network_partition: 0.3 },
  scale_out: { memory_leak: 0.5, bad_deploy: 0.2, cpu_spike: 0.85, slow_query: 0.55, network_partition: 0.3 },
  failover_to_replica: {
    memory_leak: 0.75,
    bad_deploy: 0.6,
    cpu_spike: 0.7,
    slow_query: 0.85,
    network_partition: 0.9,
  },
  circuit_breaker_isolate: {
    memory_leak: 0.6,
    bad_deploy: 0.6,
    cpu_spike: 0.6,
    slow_query: 0.6,
    network_partition: 0.65,
  },
  rollback_deploy: { bad_deploy: 0.95 },
  shed_load: { memory_leak: 0.35, bad_deploy: 0.3, cpu_spike: 0.6, slow_query: 0.5, network_partition: 0.35 },
}

const RECOVERY_SECONDS: Record<string, number> = {
  restart: 30,
  scale_out: 90,
  failover_to_replica: 45,
  circuit_breaker_isolate: 10,
  rollback_deploy: 120,
  shed_load: 15,
}

const FAULT_LOGS: Record<string, { warn: string[]; error: string[] }> = {
  memory_leak: {
    warn: ["Heap usage at {mem}% and climbing", "GC pause exceeded 800ms"],
    error: ["OutOfMemoryError: Java heap space", "Container OOM-killed, restarting worker"],
  },
  slow_query: {
    warn: ["Connection pool saturation reached {q}% of max limit", "Query latency p95 at {lat}ms"],
    error: ["slow query detected: SELECT * FROM orders JOIN transactions ... elapsed {lat}ms", "Lock wait timeout exceeded"],
  },
  network_partition: {
    warn: ["Packet loss detected on eth0 (12%)", "Heartbeat missed from peer node"],
    error: ["Connection refused: upstream unreachable", "Network partition detected, quorum lost"],
  },
  bad_deploy: {
    warn: ["New release v2.14.0 error rate above baseline", "Health check flapping after deploy"],
    error: ["NullPointerException in RequestHandler.process", "Release v2.14.0 failing readiness probe"],
  },
  cpu_spike: {
    warn: ["CPU utilization at {cpu}% sustained", "Thread pool queue depth {q}"],
    error: ["Request processing throttled: CPU saturated", "Worker watchdog timeout"],
  },
}

const CASCADE_LOGS = {
  warn: ["Upstream {dep} latency elevated, retrying", "Timeouts calling {dep} (3 of last 10)"],
  error: ["Circuit open: {dep} unavailable", "Dependency {dep} failed, returning 503"],
}

const INFO_LOGS = [
  "Health check passed",
  "Served request in {lat}ms",
  "Cache hit ratio 0.94",
  "Autoscaler: no action required",
  "Config reloaded",
]

const clamp = (v: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v))
const round = (v: number, d = 2) => Math.round(v * 10 ** d) / 10 ** d
const pick = <T,>(arr: readonly T[]) => arr[Math.floor(Math.random() * arr.length)]

function statusOf(stress: number): ServiceStatus {
  if (stress >= 0.75) return "failed"
  if (stress >= 0.35) return "degraded"
  return "healthy"
}

export class DemoEngine {
  running = true
  speed = 1
  private tick = 0
  private ts = Math.floor(Date.now() / 1000)
  private fault: Fault | null = null
  private self: Record<string, number> = {}
  private stress: Record<string, number> = {}
  private prevStress: Record<string, number> = {}
  private onset: Record<string, number | null> = {}
  private isolated = new Set<string>()
  private logs: LogLine[] = []
  private history: Record<string, number[]> = {}
  private metrics: MetricTick[] = []
  private predictions: PredictionItem[] = []
  private timer: ReturnType<typeof setTimeout> | null = null

  constructor() {
    this.reset()
    this.schedule()
  }

  reset() {
    this.tick = 0
    this.fault = null
    this.isolated.clear()
    this.logs = []
    for (const s of SERVICES) {
      this.self[s] = 0
      this.stress[s] = 0.03
      this.prevStress[s] = 0.03
      this.onset[s] = null
      this.history[s] = [0.02]
    }
    for (let i = 0; i < 5; i++) this.step()
  }

  setControl(action: "play" | "pause", speed: number) {
    this.running = action === "play"
    this.speed = speed
    this.schedule()
  }

  injectFault(service: string, type: string) {
    if (!SERVICES.includes(service as (typeof SERVICES)[number])) throw new Error(`Unknown service: ${service}`)
    if (!FAULT_TYPES.includes(type as (typeof FAULT_TYPES)[number])) throw new Error(`Unknown fault type: ${type}`)
    this.fault = { service, type, tick: this.tick }
    this.isolated.delete(service)
    this.self[service] = Math.max(this.self[service], 0.3)
    this.pushLog(service, "WARN", `Fault injected: ${type} on ${service}`)
  }

  applyStrategy(strategy: string, target: string) {
    if (!STRATEGIES[strategy]) throw new Error(`Unknown strategy: ${strategy}`)
    const faultType = this.fault?.service === target ? this.fault.type : null
    const eff = faultType ? (EFFECTIVENESS[strategy][faultType] ?? 0.15) : 0.5

    if (strategy === "circuit_breaker_isolate") {
      this.isolated.add(target)
    } else {
      this.self[target] *= 1 - eff
      this.stress[target] *= 1 - eff * 0.8
    }
    if (this.fault?.service === target && eff >= 0.6 && strategy !== "circuit_breaker_isolate") {
      this.fault = null
    }
    this.pushLog(target, "INFO", `Recovery applied: ${strategy} on ${target}`)
    this.compute()
  }

  getState(): SystemState {
    const latest = this.metrics
    const healthValues = latest.map((m): number => (m.status === "failed" ? 0 : m.status === "degraded" ? 0.5 : 1))
    const systemHealth = round(healthValues.reduce((a, b) => a + b, 0) / Math.max(1, healthValues.length))
    const cascade = this.cascade()
    const rootCause = this.rootCause(cascade.blast_radius)
    const topSuspect = rootCause[0]?.service ?? this.fault?.service ?? null
    const recovery = topSuspect ? this.recovery(topSuspect, systemHealth, cascade.blast_radius) : []

    return {
      ts: this.ts,
      tick: this.tick,
      running: this.running,
      incident: {
        active: this.fault !== null || systemHealth < 0.95 || latest.some((m) => m.status !== "healthy"),
        fault: this.fault ? { service: this.fault.service, type: this.fault.type } : null,
      },
      system_health: systemHealth,
      graph: { nodes: GRAPH_NODES, edges: GRAPH_EDGES },
      metrics: latest,
      logs: this.logs.slice(-40),
      predictions: { ts: this.ts, predictions: this.predictions },
      cascade: { ts: this.ts, ...cascade },
      root_cause: { ts: this.ts, candidates: rootCause },
      recovery: { options: recovery },
      history: { fail_prob: Object.fromEntries(Object.entries(this.history).map(([k, v]) => [k, [...v]])) },
    }
  }

  private schedule() {
    if (this.timer) clearTimeout(this.timer)
    this.timer = null
    if (!this.running) return
    const loop = () => {
      this.step()
      this.timer = setTimeout(loop, Math.max(100, 1000 / Math.max(0.1, this.speed)))
    }
    this.timer = setTimeout(loop, Math.max(100, 1000 / Math.max(0.1, this.speed)))
  }

  private step() {
    this.tick += 1
    this.ts += 1
    this.prevStress = { ...this.stress }

    for (const s of SERVICES) {
      if (this.fault?.service === s) {
        this.self[s] = clamp(this.self[s] + FAULT_RATE[this.fault.type] * (0.8 + Math.random() * 0.4))
      } else {
        this.self[s] = clamp(this.self[s] - 0.08)
      }
    }

    const next: Record<string, number> = {}
    for (const s of SERVICES) {
      let inherited = 0
      for (const e of GRAPH_EDGES) {
        if (e.source !== s) continue
        const dampen = this.isolated.has(e.target) ? 0.15 : 1
        const factor = e.kind === "hard" ? 0.92 : 0.5
        inherited = Math.max(inherited, this.prevStress[e.target] * e.weight * factor * dampen)
      }
      const blended = this.prevStress[s] + (inherited - this.prevStress[s]) * 0.45
      const noise = (Math.random() - 0.5) * 0.02
      next[s] = clamp(Math.max(this.self[s], blended) + noise, 0.01, 1)
    }
    this.stress = next

    for (const s of SERVICES) {
      if (this.stress[s] > 0.2 && this.onset[s] === null) this.onset[s] = this.tick
      if (this.stress[s] < 0.12) this.onset[s] = null
    }

    this.compute()
    this.generateLogs()
  }

  private compute() {
    this.metrics = SERVICES.map((s) => {
      const b = NODE_BASELINES[s]
      const st = this.stress[s]
      const ft = this.fault?.service === s ? this.fault.type : null
      const latMult = ft === "slow_query" ? 60 : ft === "network_partition" ? 40 : 18
      return {
        ts: this.ts,
        service: s,
        latency_p95_ms: round(b.lat * (1 + st * st * latMult) * (0.95 + Math.random() * 0.1), 1),
        error_rate: round(clamp(st * st * 0.65 + Math.random() * 0.005), 3),
        cpu: round(clamp(b.cpu + st * (ft === "cpu_spike" ? 0.65 : 0.45))),
        mem: round(clamp(b.mem + st * (ft === "memory_leak" ? 0.5 : 0.2))),
        queue_depth: Math.round(b.q * (1 + st * 4)),
        status: statusOf(st),
      }
    })

    this.predictions = SERVICES.map((s) => {
      const trend = this.stress[s] - this.prevStress[s]
      const prob = round(clamp(0.02 + this.stress[s] * 0.9 + trend * 1.5, 0.01, 0.99))
      const m = this.metrics.find((x) => x.service === s)!
      const signals: string[] = []
      if (m.latency_p95_ms > NODE_BASELINES[s].lat * 2) signals.push("latency_p95_ms")
      if (m.error_rate > 0.05) signals.push("error_rate")
      if (m.cpu > 0.7) signals.push("cpu")
      if (m.mem > 0.75) signals.push("mem")
      const worstDep = GRAPH_EDGES.filter((e) => e.source === s).sort(
        (a, b) => this.stress[b.target] - this.stress[a.target],
      )[0]
      if (worstDep && this.stress[worstDep.target] > 0.3) signals.push(`upstream:${worstDep.target}`)
      return {
        service: s,
        fail_prob: prob,
        horizon_s: Math.round(60 + (1 - prob) * 240),
        top_signals: signals.slice(0, 3),
      }
    })

    for (const p of this.predictions) {
      const h = this.history[p.service]
      h.push(p.fail_prob)
      if (h.length > HISTORY_LEN) h.splice(0, h.length - HISTORY_LEN)
    }
  }

  private probOf(s: string) {
    return this.predictions.find((p) => p.service === s)?.fail_prob ?? 0
  }

  private cascade(): { paths: CascadePath[]; blast_radius: Record<string, number> } {
    const paths: CascadePath[] = []
    for (const e of GRAPH_EDGES) {
      if (this.isolated.has(e.target)) continue
      const srcProb = this.probOf(e.target)
      if (srcProb < 0.3) continue
      const prob = round(clamp(srcProb * e.weight * (e.kind === "hard" ? 1 : 0.6)))
      if (prob < 0.18) continue
      paths.push({ from: e.target, to: e.source, prob, eta_s: Math.round(15 + (1 - prob) * 120) })
    }
    paths.sort((a, b) => b.prob - a.prob)

    const blast: Record<string, number> = {}
    for (const s of SERVICES) {
      if (this.probOf(s) < 0.3 || this.isolated.has(s)) {
        blast[s] = 0
        continue
      }
      const seen = new Set<string>()
      const queue: string[] = [s]
      while (queue.length) {
        const cur = queue.shift()!
        for (const e of GRAPH_EDGES) {
          if (e.target === cur && !seen.has(e.source) && e.source !== s) {
            seen.add(e.source)
            queue.push(e.source)
          }
        }
      }
      blast[s] = seen.size
    }
    return { paths: paths.slice(0, 10), blast_radius: blast }
  }

  private rootCause(blast: Record<string, number>): RootCauseCandidate[] {
    const stressed = SERVICES.filter((s) => this.stress[s] > 0.2)
    if (stressed.length === 0) return []

    const raw = stressed.map((s) => {
      const depStress = Math.max(
        0,
        ...GRAPH_EDGES.filter((e) => e.source === s).map((e) => this.stress[e.target] * e.weight),
      )
      const onset = this.onset[s] ?? this.tick
      const earliness = clamp((this.tick - onset) / 20)
      const value = this.stress[s] * (1 - 0.85 * clamp(depStress / Math.max(0.01, this.stress[s]))) + earliness * 0.3
      return { service: s, value: Math.max(0.01, value), depStress, onset }
    })
    raw.sort((a, b) => b.value - a.value)
    const top = raw[0].value

    return raw.slice(0, 4).map((r, i) => {
      const score = round(clamp((r.value / top) * (0.55 + 0.4 * clamp(this.stress[raw[0].service] * 1.2)), 0.05, 0.97))
      const ageS = this.tick - r.onset
      let explanation: string
      if (i === 0) {
        const signal = this.fault?.service === r.service ? `${this.fault.type.replace(/_/g, " ")} signals` : "error spikes"
        explanation = `Earliest anomaly (t-${ageS}s), ${blast[r.service] ?? 0} downstream services at risk, ${signal} in logs`
      } else {
        const upstream = GRAPH_EDGES.filter((e) => e.source === r.service).sort(
          (a, b) => this.stress[b.target] - this.stress[a.target],
        )[0]?.target
        explanation =
          upstream && r.depStress > 0.2
            ? `Latency and error degradation strongly correlated with upstream ${upstream}`
            : `Anomalous metrics since t-${ageS}s, but weaker onset signal than ${raw[0].service}`
      }
      return { service: r.service, score: i === 0 ? score : Math.min(score, 0.6), explanation }
    })
  }

  private recovery(target: string, health: number, blast: Record<string, number>): RecoveryOption[] {
    const faultType = this.fault?.service === target ? this.fault.type : null
    const radius = Math.max(1, blast[target] ?? 0)
    const options: RecoveryOption[] = []

    for (const [name, def] of Object.entries(STRATEGIES)) {
      if (def.requiresReplica && !NODE_BASELINES[target].replica) continue
      const applies = def.appliesTo === "any" || (faultType !== null && (def.appliesTo as string[]).includes(faultType))
      if (!applies) continue
      const eff = faultType ? (EFFECTIVENESS[name][faultType] ?? 0.15) : 0.5
      const saved = Math.round(radius * eff)
      const est = RECOVERY_SECONDS[name]
      const endHealth = clamp(health + (1 - health) * eff * 0.95)
      const terms: Record<string, number> = {
        services_saved: saved / radius,
        health: endHealth,
        speed: 1 - est / 180,
        low_cost: 1 - def.cost,
        low_risk: 1 - def.risk,
      }
      const score = round(SCORE_WEIGHTS.reduce((acc, w) => acc + w.weight * terms[w.key], 0))
      const projected = Array.from({ length: 6 }, (_, i) => {
        const t = i / 5
        const eased = 1 - (1 - t) ** 2
        return round(health + (endHealth - health) * eased)
      })
      options.push({
        strategy: name,
        target,
        services_saved: saved,
        est_recovery_s: est,
        cost: def.cost,
        risk: def.risk,
        score,
        recommended: false,
        rationale: `${def.description}; protects ${saved} of ${radius} at-risk dependants`,
        projected_health: projected,
      })
    }
    options.sort((a, b) => b.score - a.score)
    if (options[0]) options[0].recommended = true
    return options
  }

  private generateLogs() {
    for (const s of SERVICES) {
      const st = this.stress[s]
      const m = this.metrics.find((x) => x.service === s)!
      const fill = (msg: string, dep = "") =>
        msg
          .replace("{lat}", String(Math.round(m.latency_p95_ms)))
          .replace("{cpu}", String(Math.round(m.cpu * 100)))
          .replace("{mem}", String(Math.round(m.mem * 100)))
          .replace("{q}", String(Math.min(99, Math.round(50 + st * 50))))
          .replace("{dep}", dep)

      if (st < 0.3) continue
      if (Math.random() > 0.25 + st * 0.5) continue
      const level = st >= 0.7 ? "ERROR" : "WARN"
      const isOrigin = this.fault?.service === s
      if (isOrigin) {
        const bank = FAULT_LOGS[this.fault!.type]
        this.pushLog(s, level, fill(pick(level === "ERROR" ? bank.error : bank.warn)))
      } else {
        const dep = GRAPH_EDGES.filter((e) => e.source === s).sort(
          (a, b) => this.stress[b.target] - this.stress[a.target],
        )[0]?.target
        this.pushLog(s, level, fill(pick(level === "ERROR" ? CASCADE_LOGS.error : CASCADE_LOGS.warn), dep ?? "upstream"))
      }
    }
    if (Math.random() < 0.7) {
      const s = pick(SERVICES)
      const m = this.metrics.find((x) => x.service === s)!
      const level = Math.random() < 0.2 ? "DEBUG" : "INFO"
      this.pushLog(s, level, pick(INFO_LOGS).replace("{lat}", String(Math.round(m.latency_p95_ms))))
    }
  }

  private pushLog(service: string, level: LogLine["level"], message: string) {
    this.logs.push({ ts: this.ts + Math.random() * 0.9, service, level, message })
    if (this.logs.length > 60) this.logs.splice(0, this.logs.length - 60)
  }
}

let engine: DemoEngine | null = null
export function getDemoEngine() {
  if (!engine) engine = new DemoEngine()
  return engine
}
