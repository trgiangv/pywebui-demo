import { useEffect, useRef } from "react"
import { displayText } from "@/lib/text"
import { useBridge } from "@/providers/bridge-provider"
import { assignGroupColors } from "@/lib/color-palette"
import type { ElementRow } from "@/types"

export function useScheduleSync(
  active: boolean,
  filteredRows: ElementRow[],
  groupBy: string | undefined,
): void {
  const bridge = useBridge()
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  useEffect(() => {
    if (!active) return
    return () => {
      void bridge.resetScheduleMode()
    }
  }, [active, bridge])

  useEffect(() => {
    if (!active || filteredRows.length === 0) return

    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      const field = groupBy ?? "category"

      const groupMap = new Map<string, string[]>()
      for (const row of filteredRows) {
        const key = displayText((row as Record<string, unknown>)[field], "Unknown")
        const arr = groupMap.get(key) ?? []
        arr.push(row.element_id)
        groupMap.set(key, arr)
      }

      const groups = assignGroupColors(groupMap)

      void bridge.applyGroupOverrides(
        groups.map((g) => ({ element_ids: g.ids, color: g.color })),
        filteredRows.map((r) => r.element_id),
      )
    }, 300)

    return () => clearTimeout(debounceRef.current)
  }, [active, filteredRows, groupBy, bridge])
}
