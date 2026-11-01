const PALETTE: [number, number, number][] = [
  [66, 133, 244],
  [234, 67, 53],
  [52, 168, 83],
  [251, 188, 4],
  [171, 71, 188],
  [255, 112, 67],
  [0, 172, 193],
  [124, 179, 66],
  [233, 30, 99],
  [63, 81, 181],
  [255, 167, 38],
  [0, 150, 136],
]

export interface ColorGroup {
  label: string
  ids: string[]
  color: [number, number, number]
}

export function assignGroupColors(groups: Map<string, string[]>): ColorGroup[] {
  return Array.from(groups.entries()).map(([label, ids], i) => ({
    label,
    ids,
    color: PALETTE[i % PALETTE.length],
  }))
}

export function colorToRgba(color: [number, number, number], alpha = 1): string {
  return `rgba(${color[0]}, ${color[1]}, ${color[2]}, ${alpha})`
}

export { PALETTE }
