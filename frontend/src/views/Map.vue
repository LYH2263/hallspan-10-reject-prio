<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

const HALL_ID = 1
const data = ref<any>(null)
const candidates = ref<any[]>([])
const papers = ref<any[]>([])
const minDist = ref<number>(2)
const blockedEnabled = ref<boolean>(false)
const saving = ref(false)

async function run() {
  data.value = await api(`/seating/run?hall_id=${HALL_ID}`, { method: 'POST' })
  minDist.value = data.value.min_dist
  blockedEnabled.value = data.value.blocked_enabled
}

onMounted(async () => {
  [candidates.value, papers.value] = await Promise.all([api('/candidates'), api('/papers')])
  await run()
})

// --- 一切视图状态都由本次 run 的结果派生，前端不造原因码 ---
const blockedSet = computed(() => {
  const s = new Set<string>()
  for (const b of data.value?.blocked_seats || []) s.add(b.row + ',' + b.col)
  return s
})
const codeMap = computed<Record<string, any>>(() => data.value?.reason_codes || {})
const unplacedById = computed(() => {
  const m = new Map<number, any>()
  for (const u of data.value?.unplaced || []) if (u.candidate_id != null) m.set(u.candidate_id, u)
  return m
})

const gridStyle = computed(() =>
  data.value ? { gridTemplateColumns: `repeat(${data.value.cols}, 80px)` } : {})

const cells = computed(() => {
  if (!data.value) return []
  const map = new Map<string, any>()
  for (const a of data.value.assignments || []) map.set(a.row + ',' + a.col, a)
  const out: any[] = []
  for (let r = 0; r < data.value.rows; r++) {
    for (let c = 0; c < data.value.cols; c++) {
      const key = r + ',' + c
      if (map.has(key)) out.push(map.get(key))
      else out.push({ empty: true, row: r, col: c, blocked: blockedSet.value.has(key) })
    }
  }
  return out
})

function firstTone(cell: any) {
  const code = cell.reasons?.[0]?.code
  return codeMap.value[code]?.tone ?? 'bad'
}
function paperClass(pid: number) { return pid % 2 === 0 ? 'b' : 'a' }

// --- 配置修改：改完 PATCH 再重排，三口随同一次 run 一起变 ---
async function persistHall(patch: any) {
  saving.value = true
  try {
    const hall = await api(`/halls/${HALL_ID}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    })
    blockedEnabled.value = hall.blocked_enabled
    await run()
  } finally { saving.value = false }
}

function toggleBlocked(cell: any) {
  if (saving.value) return
  const key = cell.row + ',' + cell.col
  const cur: any[] = (data.value?.blocked_seats || []).filter(
    (b: any) => b.row + ',' + b.col !== key)
  if (!cell.blocked) cur.push({ row: cell.row, col: cell.col })
  // 一旦配置任何损坏格即视为启用禁坐；清空且关闭才会让禁坐计数归 0。
  persistHall({ blocked_seats: cur, blocked_enabled: cur.length > 0 ? true : blockedEnabled.value })
}

function setBlockedEnabled(v: boolean) {
  // 仅切换开关；关闭时后端把损坏格视为普通格，配置本身保留以便重新启用。
  persistHall({ blocked_enabled: v })
}

function saveMinDist() { persistHall({ min_manhattan: Number(minDist.value) || 1 }) }

async function changePaper(c: any, e: Event) {
  const paper_id = Number((e.target as HTMLSelectElement).value)
  await api(`/candidates/${c.id}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ paper_id }),
  })
  c.paper_id = paper_id
  await run()
}
</script>
<template>
  <h1>考场课桌网格</h1>
  <p class="sub">一次排座即唯一真相：格子禁坐态、违规高亮、行说明、未排、分类计数全部同源</p>

  <div class="card" style="display:flex;gap:1rem;align-items:center;flex-wrap:wrap">
    <label>最小曼哈顿距
      <input v-model.number="minDist" type="number" min="1" style="width:64px" @change="saveMinDist" />
    </label>
    <label>损坏禁坐
      <input type="checkbox" :checked="blockedEnabled" @change="setBlockedEnabled(($event.target as HTMLInputElement).checked)" />
    </label>
    <button class="btn" :disabled="saving" @click="run">重新排座</button>
    <span class="muted">点击空格切换“损坏禁坐”；改套卷/间距/损坏格后三口一起重算</span>
  </div>

  <div class="hs-classroom" style="margin-top:0.85rem">
    <aside class="hs-clipboard">
      <h2>考生名册</h2>
      <div v-for="c in candidates" :key="c.id" class="hs-roster-row">
        <div>
          <div>{{ c.name }}</div>
          <div class="hs-ticket">{{ c.ticket_no }}</div>
          <div v-if="unplacedById.has(c.id)" class="hs-ticket">
            未排：{{ unplacedById.get(c.id).detail }}
          </div>
        </div>
        <select :value="c.paper_id" @change="changePaper(c, $event)" title="改套卷">
          <option v-for="p in papers" :key="p.id" :value="p.id">{{ p.code }}</option>
        </select>
      </div>
    </aside>

    <div class="hs-desk-stage" v-if="data">
      <div class="hs-grid-board" :style="gridStyle">
        <div
          v-for="(cell,i) in cells" :key="i"
          class="hs-desk"
          :class="{
            empty: cell.empty && !cell.blocked,
            'hs-blocked': cell.blocked,
            'hs-viol': !cell.empty && cell.reasons?.length,
          }"
          :title="cell.blocked ? '损坏禁坐' : (cell.reasons?.map((x:any)=>x.detail).join('；') || '')"
          @click="cell.empty && toggleBlocked(cell)"
        >
          <template v-if="!cell.empty">
            <span class="hs-paper-tag" :class="paperClass(cell.paper_id)">卷{{ cell.paper_id }}</span>
            <div>{{ cell.name }}</div>
            <div
              v-for="(rs,j) in cell.reasons" :key="j"
              class="hs-reason" :class="'text-' + firstTone(cell)"
            >{{ rs.detail }}</div>
          </template>
          <template v-else-if="cell.blocked">损</template>
          <template v-else>·</template>
        </div>
      </div>
    </div>
  </div>
</template>
