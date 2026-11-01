import type { SessionSnapshot } from "@/types"

const STORAGE_KEY = "bim-dashboard-session-history"
const MAX_SNAPSHOTS = 10

export function getSessionHistory(): SessionSnapshot[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function pushSessionSnapshot(kpis: Record<string, number>): void {
  const history = getSessionHistory()
  history.push({
    timestamp: new Date().toISOString(),
    kpis,
  })

  const trimmed = history.slice(-MAX_SNAPSHOTS)

  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed))
  } catch {
    // localStorage might be full or unavailable
  }
}

export function getSparklineData(kpiKey: string): number[] {
  const history = getSessionHistory()
  return history.map((s) => s.kpis[kpiKey] ?? 0)
}
