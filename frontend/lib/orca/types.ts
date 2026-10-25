export type ServiceStatus = "healthy" | "degraded" | "failed"
export type LogLevel = "INFO" | "WARN" | "ERROR" | "DEBUG"

export interface GraphNode {
  id: string
  type: string
  criticality: number
}

export interface GraphEdge {
  source: string
  target: string
  weight: number
  kind: "hard" | "soft"
}

export interface MetricTick {
  ts: number
  service: string
  latency_p95_ms: number
  error_rate: number
  cpu: number
  mem: number
  queue_depth: number
  status: ServiceStatus
}

export interface LogLine {
  ts: number
  service: string
  level: LogLevel
  message: string
}

export interface PredictionItem {
  service: string
  fail_prob: number
  horizon_s: number
  top_signals: string[]
}

export interface CascadePath {
  from: string
  to: string
  prob: number
  eta_s: number
}

export interface RootCauseCandidate {
  service: string
  score: number
  explanation: string
}

export interface RecoveryOption {
  strategy: string
  target: string
  services_saved: number
  est_recovery_s: number
  cost: number
  risk: number
  score: number
  recommended: boolean
  rationale: string
  projected_health: number[]
}

export interface SystemState {
  ts: number
  tick: number
  running: boolean
  incident: { active: boolean; fault: { service: string; type: string } | null }
  system_health: number
  graph: { nodes: GraphNode[]; edges: GraphEdge[] }
  metrics: MetricTick[]
  logs: LogLine[]
  predictions: { ts: number; predictions: PredictionItem[] }
  cascade: { ts: number; paths: CascadePath[]; blast_radius: Record<string, number> }
  root_cause: { ts: number; candidates: RootCauseCandidate[] }
  recovery: { options: RecoveryOption[] }
  history: { fail_prob: Record<string, number[]> }
}
