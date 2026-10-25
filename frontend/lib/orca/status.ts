import type { ServiceStatus } from "./types"

export const STATUS_TEXT: Record<ServiceStatus, string> = {
  healthy: "text-healthy",
  degraded: "text-degraded",
  failed: "text-failed",
}

export const STATUS_BG: Record<ServiceStatus, string> = {
  healthy: "bg-healthy",
  degraded: "bg-degraded",
  failed: "bg-failed",
}

export const STATUS_VAR: Record<ServiceStatus, string> = {
  healthy: "var(--healthy)",
  degraded: "var(--degraded)",
  failed: "var(--failed)",
}

export function healthStatus(health: number): ServiceStatus {
  if (health >= 0.85) return "healthy"
  if (health >= 0.55) return "degraded"
  return "failed"
}

export function probStatus(prob: number): ServiceStatus {
  if (prob >= 0.7) return "failed"
  if (prob >= 0.35) return "degraded"
  return "healthy"
}

export const pct = (v: number, digits = 0) => `${(v * 100).toFixed(digits)}%`

export function formatClock(ts: number) {
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString("en-GB", { hour12: false })
}
