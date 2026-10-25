import type { GraphEdge, GraphNode } from "./types"

export const SERVICES = [
  "api-gateway",
  "auth",
  "user-service",
  "order-service",
  "payment",
  "inventory",
  "db-primary",
  "db-replica",
  "cache",
  "message-queue",
  "notification",
  "search",
] as const

export const FAULT_TYPES = [
  "memory_leak",
  "slow_query",
  "network_partition",
  "bad_deploy",
  "cpu_spike",
] as const

export const SPEEDS = [0.5, 1, 2, 4] as const

export const SCORE_WEIGHTS = [
  { key: "services_saved", label: "Services saved", weight: 0.3 },
  { key: "health", label: "Health", weight: 0.25 },
  { key: "speed", label: "Speed", weight: 0.15 },
  { key: "low_cost", label: "Low cost", weight: 0.15 },
  { key: "low_risk", label: "Low risk", weight: 0.15 },
] as const

export interface StrategyDef {
  description: string
  cost: number
  risk: number
  appliesTo: "any" | string[]
  requiresReplica?: boolean
}

export const STRATEGIES: Record<string, StrategyDef> = {
  restart: { description: "Restart the service to clear its bad state", cost: 0.3, risk: 0.5, appliesTo: "any" },
  scale_out: { description: "Add capacity to absorb load", cost: 0.5, risk: 0.2, appliesTo: "any" },
  failover_to_replica: {
    description: "Reroute dependants to the replica",
    cost: 0.4,
    risk: 0.25,
    appliesTo: "any",
    requiresReplica: true,
  },
  circuit_breaker_isolate: {
    description: "Cut calls to the failing service so failure stops spreading",
    cost: 0.25,
    risk: 0.45,
    appliesTo: "any",
  },
  rollback_deploy: { description: "Roll back the latest release", cost: 0.3, risk: 0.2, appliesTo: ["bad_deploy"] },
  shed_load: { description: "Drop low-priority traffic to protect the service", cost: 0.1, risk: 0.4, appliesTo: "any" },
}

export interface NodeBaseline {
  type: string
  criticality: number
  lat: number
  cpu: number
  mem: number
  q: number
  replica?: string
}

export const NODE_BASELINES: Record<string, NodeBaseline> = {
  "api-gateway": { type: "gateway", criticality: 1.0, lat: 80, cpu: 0.35, mem: 0.4, q: 10 },
  auth: { type: "service", criticality: 0.8, lat: 40, cpu: 0.3, mem: 0.35, q: 4 },
  "user-service": { type: "service", criticality: 0.6, lat: 60, cpu: 0.3, mem: 0.4, q: 6 },
  "order-service": { type: "service", criticality: 0.9, lat: 120, cpu: 0.4, mem: 0.45, q: 12 },
  payment: { type: "service", criticality: 0.95, lat: 150, cpu: 0.35, mem: 0.4, q: 8 },
  inventory: { type: "service", criticality: 0.7, lat: 70, cpu: 0.3, mem: 0.4, q: 6 },
  "db-primary": { type: "database", criticality: 0.95, lat: 25, cpu: 0.45, mem: 0.55, q: 15, replica: "db-replica" },
  "db-replica": { type: "database", criticality: 0.5, lat: 30, cpu: 0.35, mem: 0.5, q: 8 },
  cache: { type: "cache", criticality: 0.5, lat: 5, cpu: 0.25, mem: 0.5, q: 2 },
  "message-queue": { type: "queue", criticality: 0.6, lat: 15, cpu: 0.3, mem: 0.45, q: 20 },
  notification: { type: "service", criticality: 0.3, lat: 90, cpu: 0.2, mem: 0.3, q: 5 },
  search: { type: "service", criticality: 0.4, lat: 110, cpu: 0.4, mem: 0.45, q: 7 },
}

export const GRAPH_NODES: GraphNode[] = SERVICES.map((id) => ({
  id,
  type: NODE_BASELINES[id].type,
  criticality: NODE_BASELINES[id].criticality,
}))

const RAW_EDGES: [string, string, number, "hard" | "soft"][] = [
  ["api-gateway", "auth", 0.7, "hard"],
  ["api-gateway", "user-service", 0.6, "hard"],
  ["api-gateway", "order-service", 0.8, "hard"],
  ["api-gateway", "search", 0.4, "soft"],
  ["auth", "cache", 0.5, "soft"],
  ["auth", "db-replica", 0.6, "hard"],
  ["user-service", "db-replica", 0.6, "hard"],
  ["user-service", "cache", 0.4, "soft"],
  ["order-service", "payment", 0.8, "hard"],
  ["order-service", "inventory", 0.7, "hard"],
  ["order-service", "db-primary", 0.9, "hard"],
  ["order-service", "message-queue", 0.5, "soft"],
  ["payment", "db-primary", 0.8, "hard"],
  ["payment", "auth", 0.5, "hard"],
  ["inventory", "db-primary", 0.8, "hard"],
  ["inventory", "cache", 0.4, "soft"],
  ["search", "db-replica", 0.6, "hard"],
  ["search", "cache", 0.5, "soft"],
  ["notification", "message-queue", 0.8, "hard"],
  ["db-replica", "db-primary", 0.5, "soft"],
]

export const GRAPH_EDGES: GraphEdge[] = RAW_EDGES.map(([source, target, weight, kind]) => ({
  source,
  target,
  weight,
  kind,
}))

/** Layered layout in a 1000 x 500 viewBox: gateway on top, data stores at the bottom. */
export const NODE_POSITIONS: Record<string, { x: number; y: number }> = {
  "api-gateway": { x: 500, y: 50 },
  auth: { x: 130, y: 170 },
  "user-service": { x: 340, y: 170 },
  "order-service": { x: 560, y: 170 },
  search: { x: 760, y: 170 },
  notification: { x: 920, y: 170 },
  payment: { x: 380, y: 300 },
  inventory: { x: 650, y: 300 },
  "db-replica": { x: 180, y: 440 },
  "db-primary": { x: 480, y: 440 },
  cache: { x: 740, y: 440 },
  "message-queue": { x: 920, y: 440 },
}

export function humanize(id: string) {
  return id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
}
