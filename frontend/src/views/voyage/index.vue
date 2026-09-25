<template>
  <section class="page" data-module="voyage">
    <header class="page-head">
      <div>
        <h2>航次管理管理</h2>
        <p class="page-desc">维护航次，围绕航次编号、关联船舶、进口航次号、出口航次号做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记航次</button>
        <button class="btn" type="button" @click="exportRows">导出航次管理清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <button class="link" type="button" @click="openEdit(row)">编辑</button>
            <button class="link" type="button" @click="removeRow(row)">删除</button>
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无航次管理数据，可先登记航次</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条航次管理记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="formVisible" class="modal-mask" @click.self="closeForm">
      <div class="modal-card">
        <header class="modal-head">
          <h3>{{ formMode === 'create' ? '登记航次' : '编辑航次' }}</h3>
          <button class="link" type="button" @click="closeForm">关闭</button>
        </header>
        <form class="form-grid" @submit.prevent="submitForm">
          <label v-for="field in formFields" :key="field" class="form-item">
            <span>{{ field }}<em v-if="requiredFields.includes(field)">*</em></span>
            <input v-model="formValues[field]" :placeholder="`请输入${field}`" />
          </label>
          <footer class="modal-foot">
            <button class="btn primary" type="submit">保存</button>
            <button class="btn" type="button" @click="closeForm">取消</button>
          </footer>
        </form>
      </div>
    </div>

    <div v-if="detailVisible" class="modal-mask" @click.self="closeDetail">
      <div class="modal-card">
        <header class="modal-head">
          <h3>航次详情</h3>
          <button class="link" type="button" @click="closeDetail">关闭</button>
        </header>
        <dl v-if="detailEntry" class="detail-grid">
          <template v-for="column in columns" :key="column">
            <dt>{{ column }}</dt>
            <dd>{{ detailEntry[column] ?? '—' }}</dd>
          </template>
        </dl>
        <h4 class="attach-title">挂接单据（{{ detailAttached.length }}）</h4>
        <ul class="attach-list">
          <li v-for="item in detailAttached" :key="`${item.module}-${item.id}`">
            {{ item.label }} {{ item.code }}
          </li>
          <li v-if="!detailAttached.length" class="empty-state">该航次下暂无挂接单据</li>
        </ul>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type Attached = { module: string; label: string; code: string; id: number }

const ENDPOINT = '/api/voyage'
const columns = ["航次编号", "关联船舶", "进口航次号", "出口航次号", "预计到港", "实际到港", "航线名称", "航次状态"]
const actions = ["确认开航", "确认到港", "结航航次"]
const statuses = ["待开航", "航行中", "已到港", "已结航"]
const stats = [{"label": "航行中航次", "value": 0}, {"label": "今日到港航次", "value": 0}, {"label": "待结航航次", "value": 0}]
const formFields = ["航次编号", "关联船舶", "进口航次号", "出口航次号", "预计到港", "实际到港", "航线名称"]
const requiredFields = ["航次编号", "关联船舶", "进口航次号"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const formVisible = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const formValues = ref<Record<string, string>>({})
const editingId = ref<number | null>(null)

const detailVisible = ref(false)
const detailEntry = ref<Row | null>(null)
const detailAttached = ref<Attached[]>([])

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  formMode.value = 'create'
  formValues.value = {}
  editingId.value = null
  formVisible.value = true
}

function openEdit(row: Row) {
  formMode.value = 'edit'
  editingId.value = Number(row.id)
  formValues.value = Object.fromEntries(formFields.map((field) => [field, String(row[field] ?? '')]))
  formVisible.value = true
}

function closeForm() {
  formVisible.value = false
}

async function submitForm() {
  errorMessage.value = ''
  const isCreate = formMode.value === 'create'
  const url = isCreate ? ENDPOINT : `${ENDPOINT}/${editingId.value}`
  try {
    const response = await request(url, {
      method: isCreate ? 'POST' : 'PUT',
      body: JSON.stringify({ values: formValues.value }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message ?? payload.detail ?? '航次保存未生效，请检查后重试')
    }
    formVisible.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '航次保存失败'
  }
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const [entryRes, attachRes] = await Promise.all([
      request(`${ENDPOINT}/${row.id}`),
      request(`${ENDPOINT}/${row.id}/attachments`),
    ])
    if (!entryRes.ok || !attachRes.ok) {
      throw new Error('航次详情读取失败')
    }
    detailEntry.value = await entryRes.json()
    const attachPayload = await attachRes.json()
    detailAttached.value = attachPayload.attached ?? []
    detailVisible.value = true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '航次详情读取失败'
  }
}

function closeDetail() {
  detailVisible.value = false
}

async function removeRow(row: Row) {
  errorMessage.value = ''
  try {
    const attachRes = await request(`${ENDPOINT}/${row.id}/attachments`)
    if (!attachRes.ok) {
      throw new Error('挂接单据核对失败，请稍后重试')
    }
    const attachPayload = await attachRes.json()
    const attached: Attached[] = attachPayload.attached ?? []
    if (attached.length) {
      const lines = attached.map((item) => `${item.label} ${item.code}`).join('\n')
      window.alert(`航次 ${row['航次编号']} 下仍挂着 ${attached.length} 份单据：\n${lines}\n请先处理这些单据再删除，航次未删除。`)
      return
    }
    if (!window.confirm(`航次 ${row['航次编号']} 没有挂接单据，确认删除？`)) {
      return
    }
    const response = await request(`${ENDPOINT}/${row.id}`, { method: 'DELETE' })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message ?? payload.detail ?? '航次删除未生效')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '航次删除失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message ?? payload.detail ?? '航次管理动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '航次管理操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('航次列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '航次管理列表读取失败'
  }
}

onMounted(reload)
</script>
