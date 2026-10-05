<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

// findings 是本页唯一数据源；违规/未排是它的两个 scope 切片。
const findings = ref<any[]>([])
const reasonCodes = ref<Record<string, any>>({})

onMounted(async () => {
  const res = await api('/seating/violations?hall_id=1')
  findings.value = res.findings || []
  reasonCodes.value = res.reason_codes || {}
})

const violations = computed(() => findings.value.filter(f => f.scope === 'violation'))
const unplaced = computed(() => findings.value.filter(f => f.scope === 'unplaced'))

// 分类计数：仅对列表按 code 分桶，绝不另写一套判断；标签取自后端 reason_codes。
const tally = computed(() => {
  const m = new Map<string, number>()
  for (const f of findings.value) m.set(f.code, (m.get(f.code) || 0) + 1)
  return [...m.entries()].map(([code, n]) => ({
    code, n,
    label: reasonCodes.value[code]?.label ?? code,
    tone: reasonCodes.value[code]?.tone ?? 'muted',
  }))
})

function label(code: string) { return reasonCodes.value[code]?.label ?? code }
function tone(code: string) { return reasonCodes.value[code]?.tone ?? 'muted' }
function who(f: any) {
  return f.scope === 'violation' ? `${f.a_id} ↔ ${f.b_id}` : `#${f.candidate_id}`
}
</script>
<template>
  <h1>违规与未排</h1>
  <p class="sub">唯一列表（findings）派生：违规、未排、分类计数同源；原因码与文案以后端为准</p>

  <div class="card" style="display:flex;gap:1.2rem;flex-wrap:wrap">
    <div v-for="t in tally" :key="t.code" class="stat">
      <span class="badge" :class="'badge-' + t.tone">{{ t.label }}</span>
      <strong style="margin-left:.4rem">{{ t.n }}</strong>
    </div>
    <div v-if="!tally.length" class="muted">列表为空，分类计数全 0</div>
  </div>

  <div class="card">
    <table>
      <thead><tr><th>分类</th><th>对象</th><th>说明（与座位行说明同句）</th></tr></thead>
      <tbody>
        <tr v-for="(f,i) in findings" :key="i">
          <td><span class="badge" :class="'badge-' + tone(f.code)">{{ label(f.code) }}</span></td>
          <td>{{ who(f) }}</td>
          <td>{{ f.detail }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="!findings.length" class="muted">无违规、无未排</p>
  </div>

  <div class="card">
    <h3>违规（{{ violations.length }}）</h3>
    <div v-for="(f,i) in violations" :key="'v'+i">
      <span class="badge" :class="'badge-' + tone(f.code)">{{ label(f.code) }}</span>
      {{ f.a_id }} ↔ {{ f.b_id }}：{{ f.detail }}
    </div>
    <p v-if="!violations.length" class="muted">无违规</p>
  </div>

  <div class="card">
    <h3>未排上（{{ unplaced.length }}）</h3>
    <div v-for="(f,i) in unplaced" :key="'u'+i">
      {{ f.candidate_id != null ? '#' + f.candidate_id : '' }}：{{ f.detail }}
      <span class="badge" :class="'badge-' + tone(f.code)">{{ label(f.code) }}</span>
    </div>
    <p v-if="!unplaced.length" class="muted">无未排</p>
  </div>
</template>
