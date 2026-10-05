<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { fetchPlan, labelOf, seatNotes, store } from '../plan'

// 名册是独立数据（不属于行说明/列表/计数三口），保留全量含未排考生。
const candidates = ref<any[]>([])

async function run() {
  await fetchPlan(true)
}
onMounted(async () => {
  candidates.value = await api('/candidates')
  await fetchPlan()
})

const gridStyle = computed(() =>
  store.plan ? { gridTemplateColumns: `repeat(${store.plan.cols}, 72px)` } : {})

// 行说明与高亮都由同一份 issues 投影，禁止再另拉一套。
const notes = computed(() => seatNotes())

// 未排考生 id 集合，同样由 issues 投影，不在名册侧另算一套。
const unplacedIds = computed(
  () => new Set((store.plan?.unplaced ?? []).map((u) => u.id)),
)

const cells = computed(() => {
  if (!store.plan) return []
  const map = new Map<string, any>()
  for (const a of store.plan.assignments) map.set(a.row + ',' + a.col, a)
  const out: any[] = []
  for (let r = 0; r < store.plan.rows; r++) {
    for (let c = 0; c < store.plan.cols; c++) {
      const key = r + ',' + c
      out.push(map.get(key) || { empty: true, row: r, col: c, key })
    }
  }
  return out
})

function cellNotes(cell: any) {
  return notes.value.get(cell.row + ',' + cell.col) ?? []
}
function paperClass(pid: number) {
  return pid % 2 === 0 ? 'b' : 'a'
}
</script>
<template>
  <h1>考场课桌网格</h1>
  <p class="sub">课桌网格为主视图 · 行说明/违规列表/分类计数同源于 issues · 违规课桌高亮</p>
  <button class="btn" @click="run">重新排座</button>
  <div class="hs-classroom" style="margin-top:0.85rem">
    <aside class="hs-clipboard">
      <h2>考生名册</h2>
      <div v-for="a in candidates" :key="a.id" class="hs-roster-row">
        <div>
          <div>{{ a.name }} <span v-if="unplacedIds.has(a.id)" class="badge badge-warn">未排</span></div>
          <div class="hs-ticket">{{ a.ticket_no }}</div>
        </div>
        <div>卷{{ a.paper_id }}</div>
      </div>
    </aside>
    <div class="hs-desk-stage" v-if="store.plan">
      <div class="hs-grid-board" :style="gridStyle">
        <div
          v-for="cell in cells" :key="cell.row + ',' + cell.col"
          class="hs-desk"
          :class="{ empty: cell.empty, 'hs-viol': cellNotes(cell).length > 0 }"
          :title="cellNotes(cell).map((i) => i.detail).join('；')"
        >
          <template v-if="!cell.empty">
            <span class="hs-paper-tag" :class="paperClass(cell.paper_id)">卷{{ cell.paper_id }}</span>
            <div>{{ cell.name }}</div>
          </template>
          <template v-else>
            <template v-if="cellNotes(cell).length">
              <span class="hs-blocked">{{ cellNotes(cell).map((i) => labelOf(i.code)).join('/') }}</span>
            </template>
            <template v-else>·</template>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>
