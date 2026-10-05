<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { fetchPlan } from '../plan'
const rows = ref<any[]>([])
const msg = ref('')

onMounted(async () => {
  rows.value = await api('/halls')
  rows.value.forEach((r: any) => { r._seats = seatsText(r) })
})

// 损坏格编辑形态："r,c" 每行/逗号分隔（0 基）。
function seatsText(r: any): string {
  return (r.blocked_seats ?? []).map((s: number[]) => s.join(',')).join('；')
}
function parseSeats(text: string): number[][] {
  return text.split(/[；;\n]/).map((s) => s.trim()).filter(Boolean).map((s) => {
    const [r, c] = s.split(/[,，]/).map((n) => parseInt(n.trim(), 10))
    return [r, c]
  })
}

async function save(r: any) {
  msg.value = ''
  try {
    const updated = await api(`/halls/${r.id}`, {
      method: 'PATCH',
      body: JSON.stringify({
        min_manhattan: Number(r.min_manhattan),
        blocked_enabled: r.blocked_enabled,
        blocked_seats: parseSeats(r._seats),
      }),
    })
    Object.assign(r, updated); r._seats = seatsText(r)
    // 配置已变：刷新共享 plan，三口一起变。
    await fetchPlan(true)
    msg.value = '已保存并重算'
  } catch (e: any) {
    msg.value = '保存失败：' + e.message
  }
}
</script>
<template>
  <h1>考室</h1>
  <p class="sub">网格 / 最小间距 / 损坏禁坐（改后行说明·列表·计数一起重算）</p>
  <div class="card" v-for="r in rows" :key="r.id" :style="{ marginBottom: '0.85rem' }">
    <div style="display:flex;gap:1rem;flex-wrap:wrap;align-items:end">
      <div>
        <div class="muted">{{ r.code }} · {{ r.name }}</div>
      </div>
      <label>最小间距
        <input v-model.number="r.min_manhattan" type="number" min="1" style="width:80px" />
      </label>
      <label>启用损坏禁坐
        <input type="checkbox" v-model="r.blocked_enabled" />
      </label>
      <label>损坏格(行,列 0基)
        <input v-model="r._seats" :placeholder="'如 2,3'" style="width:160px" />
      </label>
      <button class="btn" @click="save(r)">保存并重算</button>
    </div>
  </div>
  <p v-if="msg" class="muted">{{ msg }}</p>
</template>
