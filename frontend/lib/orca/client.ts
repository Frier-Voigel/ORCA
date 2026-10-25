import { getDemoEngine } from "./demo-engine"
import type { SystemState } from "./types"

const API_BASE = process.env.NEXT_PUBLIC_ORCA_API_URL?.replace(/\/$/, "") ?? ""

export const IS_LIVE = API_BASE.length > 0
export const API_LABEL = IS_LIVE ? API_BASE : "Demo engine"

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)
    } catch {}
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) })

export async function fetchState(): Promise<SystemState> {
  if (!IS_LIVE) return getDemoEngine().getState()
  return request<SystemState>("/api/state")
}

export async function injectFault(service: string, type: string) {
  if (!IS_LIVE) return getDemoEngine().injectFault(service, type)
  await post("/api/inject-fault", { service, type })
}

export async function applyStrategy(strategy: string, target: string) {
  if (!IS_LIVE) return getDemoEngine().applyStrategy(strategy, target)
  await post("/api/apply-strategy", { strategy, target })
}

export async function setControl(action: "play" | "pause", speed: number) {
  if (!IS_LIVE) return getDemoEngine().setControl(action, speed)
  await post("/api/control", { action, speed })
}

export async function resetSimulation() {
  if (!IS_LIVE) return getDemoEngine().reset()
  await post("/api/reset")
}
