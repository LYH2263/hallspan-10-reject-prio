<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
const s = ref<any>(null)
onMounted(async () => { s.value = await api('/seating/stats?hall_id=1') })

// 分类计数完全取自后端（由 findings 列表派生），前端只负责展示标签。
const breakdown = computed(() => {
  if (!s.value) return []
  const codes = s.value.reason_codes || {}
  return Object.entries(s.value.by_code || {}).map(([code, n]) => ({
    code, n: n as number,
    label: codes[code]?.label ?? code,
    tone: codes[code]?.tone ?? 'muted',
  }))
})
</script>
<template>
  <h1>统计</h1>
  <p class="sub">分类计数由唯一列表 findings 派生；列表为空时全部分类为 0</p>
  <div class="card" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1rem">
    <div><div class="muted">已排座</div><div class="stat">{{ s?.seated ?? 0 }}</div></div>
    <div><div class="muted">未排上</div><div class="stat">{{ s?.unplaced ?? 0 }}</div></div>
    <div><div class="muted">违规数</div><div class="stat">{{ s?.violations ?? 0 }}</div></div>
    <div><div class="muted">座位容量</div><div class="stat">{{ s?.capacity ?? 0 }}</div></div>
  </div>
  <div class="card">
    <h3>按原因码分类（派生自列表）</h3>
    <div style="display:flex;gap:1rem;flex-wrap:wrap">
      <div v-for="b in breakdown" :key="b.code">
        <span class="badge" :class="'badge-' + b.tone">{{ b.label }}</span>
        <strong style="margin-left:.35rem">{{ b.n }}</strong>
      </div>
    </div>
  </div>
</template>
