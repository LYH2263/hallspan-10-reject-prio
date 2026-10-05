<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { fetchPlan } from '../plan'
const rows = ref<any[]>([])
const papers = ref<any[]>([])
const msg = ref('')

onMounted(async () => {
  [rows.value, papers.value] = await Promise.all([api('/candidates'), api('/papers')])
})

async function changePaper(c: any, paper_id: number) {
  msg.value = ''
  try {
    const updated = await api(`/candidates/${c.id}`, {
      method: 'PATCH', body: JSON.stringify({ paper_id }),
    })
    Object.assign(c, updated)
    await fetchPlan(true)   // 套卷变更：三口一起重算
    msg.value = `已更新 ${c.name} 的套卷并重算`
  } catch (e: any) { msg.value = '保存失败：' + e.message }
}
</script>
<template>
  <h1>考生名册</h1>
  <p class="sub">夹板名册样式 · 调整套卷后排座图/违规/统计同步重算</p>
  <div class="hs-clipboard" style="max-width:520px">
    <h2>考生名册 · Clipboard</h2>
    <div v-for="r in rows" :key="r.id" class="hs-roster-row">
      <div>
        <div>{{ r.name }}</div>
        <div class="hs-ticket">{{ r.ticket_no }}</div>
      </div>
      <label>
        卷
        <select :value="r.paper_id" @change="changePaper(r, Number(($event.target as HTMLSelectElement).value))">
          <option v-for="p in papers" :key="p.id" :value="p.id">{{ p.code }}</option>
        </select>
      </label>
    </div>
  </div>
  <p v-if="msg" class="muted">{{ msg }}</p>
</template>
