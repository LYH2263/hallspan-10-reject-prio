import { reactive } from 'vue'
import { api } from './api'

// 唯一真相源：整页只持有这一份 plan。
// 行说明（座位格）、违规列表、分类计数全部由 plan.issues 派生，
// 前端不定义任何原因码——label/category 一律用后端下发的 reason_codes。

export interface Issue {
  code: string
  subject: 'seat' | 'seat_pair' | 'candidate'
  detail: string
  a_id: number | null
  a_name: string | null
  b_id: number | null
  b_name: string | null
  row: number | null
  col: number | null
  b_row: number | null
  b_col: number | null
}

export interface Plan {
  rows: number
  cols: number
  assignments: any[]
  issues: Issue[]
  unplaced: { id: number; name: string; reason: string; detail: string }[]
  reason_codes: Record<string, { label: string; category: string }>
  stats: Record<string, any>
  hall?: { id: number; name: string; min_manhattan: number }
}

export const store = reactive<{ plan: Plan | null }>({ plan: null })

export async function fetchPlan(forceRun = false): Promise<Plan> {
  const path = '/seating/latest?hall_id=1'
  const plan = forceRun
    ? await api<Plan>('/seating/run?hall_id=1', { method: 'POST' })
    : await api<Plan>(path)
  store.plan = plan
  return plan
}

const seatKey = (r: number, c: number) => `${r},${c}`

// 行说明投影：每个座位命中的 issue（去重，保持后端 REASON_CODES 稳定顺序）。
export function seatNotes(): Map<string, Issue[]> {
  const out = new Map<string, Issue[]>()
  const add = (r: number | null, c: number | null, it: Issue) => {
    if (r == null || c == null) return
    const k = seatKey(r, c)
    const arr = out.get(k)
    if (!arr) out.set(k, [it])
    else if (!arr.some((x) => x.code === it.code && x.subject === it.subject)) arr.push(it)
  }
  for (const it of store.plan?.issues ?? []) {
    add(it.row, it.col, it)
    if (it.subject === 'seat_pair') add(it.b_row, it.b_col, it)
  }
  return out
}

export function candidateSeatedIds(): Set<number> {
  return new Set((store.plan?.assignments ?? []).map((a) => a.candidate_id))
}

// 分类计数：严格由 issues 列表 reduce 而来；列表为空则全 0。
export function countByCode(): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const code of Object.keys(store.plan?.reason_codes ?? {})) counts[code] = 0
  for (const it of store.plan?.issues ?? []) {
    if (!(it.code in counts)) {
      // 冒码：后端发了前端码表没有的原因，直接抛出，三口对不齐即失败。
      throw new Error(`未知原因码 ${it.code}：前端原因码表与后端不一致`)
    }
    counts[it.code] += 1
  }
  return counts
}

export function labelOf(code: string): string {
  return store.plan?.reason_codes?.[code]?.label ?? code
}
