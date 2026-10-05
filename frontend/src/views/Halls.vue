<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
onMounted(async () => { rows.value = await api('/halls') })
</script>
<template>
  <h1>考室</h1>
  <p class="sub">考室网格、最小曼哈顿间距与损坏禁坐配置（损坏格可在排座图点击切换）</p>
  <div class="card">
    <table>
      <thead>
        <tr><th>编码</th><th>名称</th><th>行</th><th>列</th><th>最小间距</th><th>损坏禁坐</th><th>损坏格</th></tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id ?? JSON.stringify(r)">
          <td>{{ r.code }}</td><td>{{ r.name }}</td>
          <td>{{ r.rows }}</td><td>{{ r.cols }}</td><td>{{ r.min_manhattan }}</td>
          <td>
            <span class="badge" :class="r.blocked_enabled ? 'badge-bad' : 'badge-ok'">
              {{ r.blocked_enabled ? '已启用' : '未启用' }}
            </span>
          </td>
          <td>
            <span v-if="!r.blocked_enabled" class="muted">—（禁坐计数必为 0）</span>
            <span v-else>{{ (r.blocked_seats || []).map((b: any) => `(${b.row},${b.col})`).join(' ') || '无' }}</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
