<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { fetchPlan, labelOf, store } from '../plan'

onMounted(fetchPlan)

// 列表即唯一真相：违规与未排都从同一份 issues 筛，前端不另造原因码。
const issues = computed(() => store.plan?.issues ?? [])
const violationIssues = computed(() =>
  issues.value.filter((i) => store.plan?.reason_codes?.[i.code]?.category === 'violation'))
const unplacedIssues = computed(() => issues.value.filter((i) => i.code === 'unplaced'))

function who(i: any) {
  return [i.a_name, i.b_name].filter(Boolean).join(' ↔ ')
}
</script>
<template>
  <h1>违规</h1>
  <p class="sub">违规/未排唯一真相列表 · 分类计数与排座图行说明均由此派生</p>
  <div class="card">
    <table>
      <thead><tr><th>类型</th><th>对象</th><th>说明</th></tr></thead>
      <tbody>
        <tr v-for="(v, i) in violationIssues" :key="i">
          <td><span class="badge badge-bad">{{ labelOf(v.code) }}</span></td>
          <td>{{ who(v) }}</td>
          <td>{{ v.detail }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="!violationIssues.length" class="muted">无违规</p>
  </div>
  <div class="card" v-if="unplacedIssues.length">
    <h3>未排上</h3>
    <table>
      <thead><tr><th>考生</th><th>原因</th><th>说明</th></tr></thead>
      <tbody>
        <tr v-for="(u, i) in unplacedIssues" :key="i">
          <td>{{ u.a_name }}</td>
          <td><span class="badge badge-warn">{{ labelOf(u.code) }}</span></td>
          <td>{{ u.detail }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
