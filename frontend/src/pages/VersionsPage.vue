<template>
  <PageFrame subtitle="Every state of this job's plan. Versions lock when their document goes for approval or is submitted. Tick versions to compare them.">
    <template #actions>
      <Button variant="solid" :disabled="!ws.plan.can_write" @click="openCreate(null)">
        <template #prefix><Icon name="plus" :size="13" /></template>
        New version
      </Button>
    </template>

    <!-- negotiation: what each round sent to the client cost us, against the opening offer -->
    <div v-if="history.length" class="rounded-xl border border-outline-gray-2 bg-surface-base">
      <div class="border-b border-outline-gray-1 px-4 py-2.5 text-sm font-semibold text-ink-gray-9">Negotiation</div>
      <div class="overflow-x-auto">
        <table class="w-full text-sm tabular-nums">
          <thead>
            <tr class="bg-surface-gray-1 text-sm text-ink-gray-6">
              <th class="px-4 py-2 text-left font-normal">Round</th>
              <th class="px-4 py-2 text-right font-normal">Client price</th>
              <th class="px-4 py-2 text-right font-normal">Cost</th>
              <th class="px-4 py-2 text-right font-normal">Margin</th>
              <th class="px-4 py-2 text-right font-normal">Price conceded</th>
              <th class="px-4 py-2 text-right font-normal">Cost recovered</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in history" :key="row.name" class="border-t border-outline-gray-1">
              <td class="px-4 py-2">
                <span class="cp-chip" :class="LOCK_TONE[row.kind]">{{ row.label }}</span>
              </td>
              <td class="px-4 py-2 text-right">{{ fmt.number(row.selling) }}</td>
              <td class="px-4 py-2 text-right">{{ fmt.number(row.cost) }}</td>
              <td class="px-4 py-2 text-right">{{ fmt.percent(row.margin) }}</td>
              <td class="px-4 py-2 text-right" :class="index && opening.selling - row.selling > 0 ? 'text-ink-red-6' : 'text-ink-gray-5'">
                {{ index ? fmt.number(opening.selling - row.selling) : '—' }}
              </td>
              <td class="px-4 py-2 text-right" :class="index && opening.cost - row.cost > 0 ? 'text-ink-green-6' : 'text-ink-gray-5'">
                {{ index ? fmt.number(opening.cost - row.cost) : '—' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="overflow-x-auto rounded-xl border border-outline-gray-2 bg-surface-base">
      <table class="w-full min-w-[900px] text-sm tabular-nums">
        <thead>
          <tr class="border-b border-outline-gray-1 bg-surface-gray-1 text-sm text-ink-gray-6">
            <th class="w-10 px-3 py-2"></th>
            <th class="px-3 py-2 text-left font-normal">Version</th>
            <th class="px-3 py-2 text-left font-normal">State</th>
            <th class="px-3 py-2 text-left font-normal">Document</th>
            <th class="px-3 py-2 text-right font-normal">Cost</th>
            <th class="px-3 py-2 text-right font-normal">Selling</th>
            <th class="px-3 py-2 text-right font-normal">Profit</th>
            <th class="px-3 py-2 text-right font-normal">Margin</th>
            <th class="px-3 py-2 text-left font-normal">Created</th>
            <th class="w-10 px-3 py-2"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="ver in ordered" :key="ver.name" class="group border-b border-outline-gray-1 last:border-0 hover:bg-surface-gray-1">
            <td class="px-3 py-2.5">
              <input type="checkbox" class="cursor-pointer" :checked="shown.has(ver.name)" @change="toggleColumn(ver.name)" />
            </td>
            <td class="px-3 py-2.5">
              <button class="text-left" @click="open(ver.name)">
                <span class="font-semibold text-ink-gray-9">V{{ ver.version_no }}</span>
                <span class="ml-1.5 text-ink-gray-8">{{ ver.version_name }}</span>
                <span v-if="ver.name === focusVersion?.name" class="cp-chip ml-2 bg-surface-gray-2 text-ink-gray-7">open</span>
              </button>
              <div v-if="ver.reason" class="mt-0.5 max-w-[320px] truncate text-xs text-ink-gray-5" :title="ver.reason">“{{ ver.reason }}”</div>
            </td>
            <td class="px-3 py-2.5">
              <span v-if="ver.status === 'Working'" class="cp-chip bg-surface-green-2 text-ink-green-8">Editable</span>
              <span v-else class="cp-chip" :class="LOCK_TONE[ver.lock_kind] || LOCK_TONE.Superseded">
                <span class="lucide-lock size-3" /> {{ ver.lock_reason || 'Locked' }}
              </span>
            </td>
            <td class="px-3 py-2.5 text-xs text-ink-gray-6">
              <a v-if="ver.source_name" class="hover:underline" :href="deskPath(ver.source_doctype, ver.source_name)" target="_blank" @click.prevent="openPanel(ver.source_doctype, ver.source_name)">
                {{ ver.source_doctype }} {{ ver.source_name }}
              </a>
            </td>
            <td class="px-3 py-2.5 text-right">{{ fmt.number(ver.total_cost) }}</td>
            <td class="px-3 py-2.5 text-right">{{ fmt.number(ver.total_selling) }}</td>
            <td class="px-3 py-2.5 text-right" :class="ver.total_profit < 0 ? 'text-ink-red-6' : ''">{{ fmt.number(ver.total_profit) }}</td>
            <td class="px-3 py-2.5 text-right">{{ fmt.percent(ver.margin_pct) }}</td>
            <td class="px-3 py-2.5 text-xs text-ink-gray-6">
              {{ ownerName(ver.owner) }}<br /><span class="text-ink-gray-5" :title="fullDate(ver.creation)">{{ timeAgo(ver.creation) }}</span>
            </td>
            <td class="px-3 py-2.5 text-right">
              <Dropdown :options="menu(ver)" placement="right">
                <button class="flex h-7 w-7 items-center justify-center rounded text-ink-gray-5 hover:bg-surface-gray-3">
                  <Icon name="dots" :size="14" />
                </button>
              </Dropdown>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="compared.length > 1" class="rounded-xl border border-outline-gray-2 bg-surface-base">
      <div class="border-b border-outline-gray-1 px-4 py-2.5 text-sm font-semibold text-ink-gray-9">Comparison</div>
      <div class="overflow-x-auto">
        <table class="w-full text-sm tabular-nums">
          <thead>
            <tr class="bg-surface-gray-1 text-sm text-ink-gray-6">
              <th class="px-4 py-2 text-left font-normal"></th>
              <th v-for="ver in compared" :key="ver.name" class="px-4 py-2 text-right font-normal">V{{ ver.version_no }} {{ ver.version_name }}</th>
              <th class="px-4 py-2 text-right font-normal">Δ vs first</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="metric in metrics" :key="metric.key" class="border-t border-outline-gray-1">
              <td class="px-4 py-2 text-ink-gray-6">{{ metric.label }}</td>
              <td v-for="ver in compared" :key="ver.name" class="px-4 py-2 text-right">{{ metric.show(ver[metric.key]) }}</td>
              <td class="px-4 py-2 text-right" :class="deltaTone(metric, delta(metric))">{{ metric.pct ? delta(metric).toFixed(1) + ' pts' : fmt.signed(delta(metric)) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </PageFrame>
</template>

<script setup>
import PageFrame from '../components/PageFrame.vue'
import { computed, inject } from 'vue'
import { useRouter } from 'vue-router'
import { Button, Dropdown } from 'frappe-ui'
import Icon from '../components/Icon.vue'
import { fullDate, timeAgo } from '../format'
import { LOCK_TONE } from '../locks'

const { ws, planName, fmt, focusVersion, focusOn, toggleColumn, openCreate, deskPath, openPanel } = inject('cp')
const router = useRouter()


const shown = computed(() => new Set(ws.value.columns.map((column) => column.version)))
const ordered = computed(() => [...ws.value.versions].sort((a, b) => b.version_no - a.version_no))
const compared = computed(() => ws.value.versions.filter((ver) => shown.value.has(ver.name)).sort((a, b) => a.version_no - b.version_no))
const history = computed(() => ws.value.summary?.history || [])
const opening = computed(() => history.value[0])

const ownerName = (user) => (user || '').split('@')[0]

const metrics = [
  { key: 'total_cost', label: 'Internal cost', show: fmt.value.number, bad: 'up' },
  { key: 'total_selling', label: 'Client selling', show: fmt.value.number },
  { key: 'total_profit', label: 'Profit', show: fmt.value.number, bad: 'down' },
  { key: 'margin_pct', label: 'Margin', show: (v) => fmt.value.percent(v), pct: true, bad: 'down' },
]

function delta(metric) {
  const list = compared.value
  return (list[list.length - 1][metric.key] || 0) - (list[0][metric.key] || 0)
}

function deltaTone(metric, value) {
  if (!value || !metric.bad) return 'text-ink-gray-6'
  const worse = metric.bad === 'up' ? value > 0 : value < 0
  return worse ? 'text-ink-red-6' : 'text-ink-green-6'
}

async function open(name) {
  await focusOn(name)
  router.push({ name: 'plan', params: { plan: planName } })
}

function menu(ver) {
  return [
    { label: ver.can_edit ? 'Open and edit' : 'Open', onClick: () => open(ver.name) },
    { label: `New version from V${ver.version_no}…`, onClick: () => openCreate(ver.name) },
  ]
}
</script>
