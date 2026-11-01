/** Must match `PROTOCOL` in `config.py` in the pushbutton `lib`. */
export const SUPPORTED_PROTOCOL = 1

export interface RevitSession {
  base: string
  token: string
}

interface Health {
  protocol?: number
  pid?: number
  revit?: string
}

const STORAGE_KEY = "bim-revit-session"

function fromUrl(): RevitSession | null {
  const port = Number(new URLSearchParams(window.location.search).get("port"))
  const token = new URLSearchParams(window.location.hash.slice(1)).get("token")
  if (!Number.isInteger(port) || port <= 0 || !token) return null
  return { base: `http://127.0.0.1:${port}`, token }
}

export function readSession(): RevitSession | null {
  try {
    const fromAddress = fromUrl()
    if (fromAddress) {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(fromAddress))
      window.history.replaceState(null, "", window.location.pathname)
      return fromAddress
    }
    const saved = sessionStorage.getItem(STORAGE_KEY)
    return saved ? (JSON.parse(saved) as RevitSession) : null
  } catch {
    return fromUrl()
  }
}

export async function checkSession(session: RevitSession): Promise<void> {
  let health: Health
  try {
    const res = await fetch(`${session.base}/api/health`)
    health = (await res.json()) as Health
  } catch {
    throw new Error(
      `Cannot reach Revit at ${session.base}. Is its BIM Dashboard connection window still open?`,
    )
  }
  if (health.protocol !== SUPPORTED_PROTOCOL) {
    throw new Error(
      `This page speaks protocol ${SUPPORTED_PROTOCOL} but Revit (PID ${health.pid ?? "?"}) speaks ${health.protocol ?? "an unknown one"}. Update the pyRevit extension or reopen the page from it.`,
    )
  }
}
