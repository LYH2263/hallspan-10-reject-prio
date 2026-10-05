<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { countByCode, fetchPlan, labelOf, store } from '../plan'

onMounted(fetchPlan)

// 分类计数由 issues 列表派生，而非另读一个独立计数器。
const byCode = computed(() => countByCode())
const codeOrder = computed(() => Object.keys(store.plan?.reason_codes ?? {}))

const mismatch = computed(() => {
  const s = store.plan?.stats
  if (!s) return ''
  // 三口同码自检：列表 reduce 出来的计数必须等于后端 stats.by_code。
  for (const k of codeOrder.value) {
    if ((s.by_code?.[k] ?? 0) !== byCode.value[k]) return `分类 ${k} 对不齐`
  }
  const viol = codeOrder.value
    .filter((k) => store.plan?.reason_codes?.[k]?.category === 'violation')
    .reduce((n, k) => n + byCode.value[k], 0)
  if (viol !== s.violations) return '违规总数对不齐'
  return ''
})
</script>
<template>
  <h1>统计</h1>
  <p class="sub">分类计数全部由违规/未排列表现场 reduce · 列表为空则各项为 0</p>
  <div class="card" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1rem">
    <div><div class="muted">已排座</div><div class="stat">{{ store.plan?.stats.seated ?? 0 }}</div></div>
    <div><div class="muted">未排上</div><div class="stat">{{ byCode.unplaced ?? 0 }}</div></div>
    <div><div class="muted">违规数</div><div class="stat">{{ store.plan?.stats.violations ?? 0 }}</div></div>
    <div><div class="muted">座位容量</div><div class="stat">{{ store.plan?.stats.capacity ?? 0 }}</div></div>
  </div>
  <div class="card">
    <h3>按原因分类（派生自列表）</h3>
    <table>
      <thead><tr><th>原因</th><th>条数</th></tr></thead>
      <tbody>
        <tr v-for="code in codeOrder" :key="code">
          <td>{{ labelOf(code) }}</td>
          <td>{{ byCode[code] }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="mismatch" class="badge badge-bad">三口对不齐：{{ mismatch }}</p>
    <p v-else class="muted">行说明 / 列表 / 计数三口一致</p>
  </div>
</template>
