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
            <button class="link danger" type="button" @click="askDelete(row)">删除</button>
            <template v-for="action in actions" :key="action">
              <button class="link" type="button" @click="runAction(action, row)">{{ action }}</button>
            </template>
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

    <!-- 详情：与列表、接口同源，并列出航次下挂着的全部单据 -->
    <div v-if="detailRow" class="modal-mask" @click.self="closeDetail">
      <div class="modal">
        <h3>航次详情</h3>
        <dl class="detail-grid">
          <template v-for="field in detailFields" :key="field">
            <dt>{{ field }}</dt>
            <dd>{{ detailRow.entry[field] ?? '—' }}</dd>
          </template>
        </dl>
        <h4>挂账单据</h4>
        <p v-if="!detailRow.references.length" class="muted">该航次下暂未挂接装卸任务、理货单、单证或堆存记录。</p>
        <div v-for="group in detailRow.references" :key="group.module" class="ref-group">
          <strong>{{ group.label }}（{{ group.items.length }} 条）</strong>
          <ul>
            <li v-for="item in group.items" :key="String(item.id)">
              {{ item[group.code_field] }} <span class="muted">（{{ item.status ?? '—' }}）</span>
            </li>
          </ul>
        </div>
        <div class="modal-foot">
          <button class="btn" type="button" @click="closeDetail">关闭</button>
        </div>
      </div>
    </div>

    <!-- 登记 / 编辑：改的是同一条正本，保存后列表、详情、接口一致 -->
    <div v-if="formVisible" class="modal-mask" @click.self="closeForm">
      <div class="modal">
        <h3>{{ formMode === 'create' ? '登记航次' : '编辑航次' }}</h3>
        <p class="muted">同一进口航次号全平台只保留一条；更换关联船舶后，挂账单据仍归属本航次。</p>
        <div class="form-grid">
          <label v-for="field in formFields" :key="field" class="form-item">
            <span>{{ field }}<em v-if="requiredFields.includes(field)">*</em></span>
            <input v-model="formValues[field]" :placeholder="`请输入${field}`" />
          </label>
        </div>
        <div class="modal-foot">
          <button class="btn" type="button" @click="closeForm">取消</button>
          <button class="btn primary" type="button" :disabled="saving" @click="submitForm">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 删除确认：先把挂着的单据说清楚 -->
    <div v-if="deleteTarget" class="modal-mask" @click.self="closeDelete">
      <div class="modal">
        <h3>删除航次</h3>
        <p>
          确定删除航次「{{ deleteTarget['航次编号'] }}」（进口航次号 {{ deleteTarget['进口航次号'] }}，
          关联船舶 {{ deleteTarget['关联船舶'] }}）吗？
        </p>
        <div v-if="deleteRefs.length" class="ref-warning">
          <strong>该航次下还挂着以下单据，删除前请先确认：</strong>
          <div v-for="group in deleteRefs" :key="group.module" class="ref-group">
            {{ group.label }}（{{ group.items.length }} 条）：
            <span v-for="item in group.items" :key="String(item.id)" class="ref-chip">{{ item[group.code_field] }}</span>
          </div>
          <p class="muted">单据不会被删除；选择「保留单据并解除关联」后，单据上的关联航次会被清空。</p>
        </div>
        <p v-else class="muted">该航次下没有挂账单据，可直接删除。</p>
        <div class="modal-foot">
          <button class="btn" type="button" @click="closeDelete">取消</button>
          <button
            v-if="deleteRefs.length"
            class="btn"
            type="button"
            :disabled="deleting"
            @click="confirmDelete(true)"
          >
            保留单据并解除关联后删除
          </button>
          <button class="btn danger" type="button" :disabled="deleting" @click="confirmDelete(false)">
            {{ deleting ? '删除中…' : deleteRefs.length ? '先去处理单据' : '确认删除' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type RefGroup = {
  module: string
  label: string
  code_field: string
  items: Array<Record<string, string | number | null>>
}
type Detail = { entry: Row; references: RefGroup[] }

const ENDPOINT = '/api/voyage'
const columns = ["航次编号", "关联船舶", "进口航次号", "出口航次号", "预计到港", "实际到港", "航线名称", "航次状态"]
const detailFields = ["id", ...columns]
const formFields = ["航次编号", "关联船舶", "进口航次号", "出口航次号", "预计到港", "实际到港", "航线名称"]
const requiredFields = ["航次编号", "关联船舶", "进口航次号"]
const actions = ["确认开航", "确认到港", "结航航次"]
const stats = [{"label": "航行中航次", "value": 0}, {"label": "今日到港航次", "value": 0}, {"label": "待结航航次", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const detailRow = ref<Detail | null>(null)
const formVisible = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const formValues = ref<Record<string, string>>({})
const formEditId = ref<number | null>(null)
const saving = ref(false)

const deleteTarget = ref<Row | null>(null)
const deleteRefs = ref<RefGroup[]>([])
const deleting = ref(false)

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function emptyForm() {
  return Object.fromEntries(formFields.map((field) => [field, '']))
}

function openCreate() {
  formMode.value = 'create'
  formValues.value = emptyForm()
  formEditId.value = null
  formVisible.value = true
}

function openEdit(row: Row) {
  formMode.value = 'edit'
  formValues.value = Object.fromEntries(formFields.map((field) => [field, String(row[field] ?? '')]))
  formEditId.value = Number(row.id)
  formVisible.value = true
}

function closeForm() {
  formVisible.value = false
}

async function submitForm() {
  errorMessage.value = ''
  saving.value = true
  const url = formMode.value === 'create' ? ENDPOINT : `${ENDPOINT}/${formEditId.value}`
  const method = formMode.value === 'create' ? 'POST' : 'PUT'
  try {
    const response = await request(url, { method, body: JSON.stringify({ values: formValues.value }) })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '航次保存失败')
    }
    formVisible.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '航次保存失败'
  } finally {
    saving.value = false
  }
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('航次详情读取失败')
    }
    detailRow.value = (await response.json()) as Detail
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '航次详情读取失败'
  }
}

function closeDetail() {
  detailRow.value = null
}

async function askDelete(row: Row) {
  errorMessage.value = ''
  deleteTarget.value = row
  deleteRefs.value = []
  try {
    const response = await request(`${ENDPOINT}/${row.id}/references`)
    if (!response.ok) {
      throw new Error('挂账单据读取失败')
    }
    const payload = (await response.json()) as { references: RefGroup[] }
    deleteRefs.value = payload.references ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '挂账单据读取失败'
  }
}

function closeDelete() {
  deleteTarget.value = null
  deleteRefs.value = []
}

async function confirmDelete(force: boolean) {
  if (!deleteTarget.value) return
  // 仍有挂账单据且没有选择解除关联时，不执行删除，只提示先处理。
  if (!force && deleteRefs.value.length) {
    errorMessage.value = '该航次下还有挂账单据，请先处理，或选择「保留单据并解除关联后删除」'
    return
  }
  deleting.value = true
  errorMessage.value = ''
  try {
    const response = await request(
      `${ENDPOINT}/${deleteTarget.value.id}?force=${force ? 'true' : 'false'}`,
      { method: 'DELETE' },
    )
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message || '航次删除失败')
    }
    closeDelete()
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '航次删除失败'
  } finally {
    deleting.value = false
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('航次管理动作未生效，请稍后重试')
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

<style scoped>
.link.danger,
.btn.danger { color: #b42318; }
.btn.danger { border-color: #f0a9a2; background: #fff5f4; }
.modal-mask {
  position: fixed; inset: 0; background: rgba(15, 23, 42, 0.45);
  display: flex; align-items: center; justify-content: center; z-index: 100;
}
.modal {
  background: #fff; border-radius: 8px; padding: 18px 20px;
  width: 640px; max-width: calc(100vw - 40px); max-height: 82vh; overflow: auto;
}
.modal h3 { margin: 0 0 8px; font-size: 16px; }
.modal h4 { margin: 14px 0 6px; font-size: 14px; }
.modal-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.muted { color: var(--muted); font-size: 12px; }
.detail-grid {
  display: grid; grid-template-columns: 120px 1fr; gap: 4px 12px;
  margin: 0; font-size: 13px;
}
.detail-grid dt { color: var(--muted); }
.detail-grid dd { margin: 0; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 14px; }
.form-item span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 2px; }
.form-item em { color: #b42318; font-style: normal; margin-left: 2px; }
.form-item input { width: 100%; padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; }
.ref-group { font-size: 13px; margin: 6px 0; }
.ref-group ul { margin: 4px 0 0; padding-left: 18px; }
.ref-warning {
  border: 1px solid #f0d8a8; background: #fffaeb; border-radius: 6px;
  padding: 10px 12px; font-size: 13px;
}
.ref-chip {
  display: inline-block; margin: 2px 4px 0 0; padding: 1px 8px;
  background: #fff; border: 1px solid var(--border); border-radius: 10px; font-size: 12px;
}
</style>
