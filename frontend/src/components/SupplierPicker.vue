<template>
  <div class="grid gap-2 text-sm">
    <!-- multi-select field: chosen suppliers as chips, type to filter the list below -->
    <div class="cp-input flex h-auto min-h-8 flex-wrap items-center gap-1 py-1" @click="inputEl?.focus()">
      <span
        v-for="name in modelValue"
        :key="name"
        class="cp-chip"
        :class="isDivision(name) ? 'bg-surface-blue-2 text-ink-blue-8' : 'bg-surface-gray-2 text-ink-gray-8'"
      >
        {{ name }}
        <button class="text-ink-gray-5 hover:text-ink-red-6" :title="`Remove ${name}`" @click.stop="toggle(name)">
          <span class="lucide-x size-3" />
        </button>
      </span>
      <input
        ref="inputEl"
        v-model="filter"
        class="min-w-[140px] flex-1 border-0 bg-transparent p-0 text-sm shadow-none outline-none focus:ring-0"
        :placeholder="modelValue.length ? 'Add another…' : 'Type to find suppliers…'"
        @keydown.enter.prevent="pickFirst"
        @keydown.backspace="!filter && modelValue.length && toggle(modelValue[modelValue.length - 1])"
      />
    </div>

    <div class="max-h-64 overflow-auto rounded-lg border border-outline-gray-2">
      <div v-if="loading" class="px-3 py-2 text-ink-gray-5">Loading suppliers…</div>
      <template v-for="group in groups" :key="group.label">
        <div v-if="group.rows.length" class="sticky top-0 flex items-center justify-between bg-surface-gray-1 px-3 py-1 text-[13px] font-normal text-ink-gray-6">
          {{ group.label }}
          <button v-if="group.label === 'Divisions'" class="text-ink-gray-7 underline-offset-2 hover:underline" @click="selectAll(group.rows)">Select all</button>
        </div>
        <label
          v-for="row in group.rows"
          :key="row.name"
          class="flex cursor-pointer items-center gap-2.5 px-3 py-1.5 hover:bg-surface-gray-1"
        >
          <input type="checkbox" :checked="modelValue.includes(row.name)" @change="toggle(row.name)" />
          <span class="text-ink-gray-9"><template v-for="(part, i) in marked(row.name)" :key="i"><b v-if="part.hit" class="text-ink-gray-9 underline decoration-ink-gray-4 underline-offset-2">{{ part.text }}</b><template v-else>{{ part.text }}</template></template></span>
          <span class="truncate text-xs text-ink-gray-5">{{ row.detail }}</span>
        </label>
      </template>
      <div v-if="!loading && !groups.some((g) => g.rows.length)" class="px-3 py-2 text-ink-gray-5">No supplier matches “{{ filter }}”.</div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  divisions: { type: Array, default: () => [] }, // [{ supplier, division, cost_center }]
})
const emit = defineEmits(['update:modelValue'])

const inputEl = ref(null)
const filter = ref('')
const all = ref([])
const loading = ref(true)

onMounted(async () => {
  try {
    all.value = (await api.listSuppliers()) || []
  } finally {
    loading.value = false
  }
  inputEl.value?.focus()
})

const divisionOf = computed(() => new Map(props.divisions.map((d) => [d.supplier, d])))
const isDivision = (name) => divisionOf.value.has(name)

function matches(row) {
  const needle = filter.value.trim().toLowerCase()
  return !needle || [row.name, row.supplier_name, row.supplier_group].some((v) => v && v.toLowerCase().includes(needle))
}

const groups = computed(() => {
  const rows = all.value.filter(matches)
  const division = rows
    .filter((r) => isDivision(r.name))
    .map((r) => ({ name: r.name, detail: `${divisionOf.value.get(r.name).division} · ${divisionOf.value.get(r.name).cost_center}` }))
  const external = rows.filter((r) => !isDivision(r.name)).map((r) => ({ name: r.name, detail: r.supplier_group || '' }))
  return [
    { label: 'Divisions', rows: division },
    { label: 'External suppliers', rows: external },
  ]
})

function toggle(name) {
  const next = props.modelValue.includes(name) ? props.modelValue.filter((n) => n !== name) : [...props.modelValue, name]
  emit('update:modelValue', next)
}

function selectAll(rows) {
  emit('update:modelValue', [...new Set([...props.modelValue, ...rows.map((r) => r.name)])])
}

/** Enter adds the first match, so typing a few letters + Enter picks a supplier. */
function pickFirst() {
  const first = groups.value.flatMap((g) => g.rows).find((r) => !props.modelValue.includes(r.name))
  if (first) toggle(first.name)
  filter.value = ''
}

function marked(value) {
  const needle = filter.value.trim().toLowerCase()
  const at = needle ? value.toLowerCase().indexOf(needle) : -1
  if (at < 0) return [{ text: value, hit: false }]
  return [
    { text: value.slice(0, at), hit: false },
    { text: value.slice(at, at + needle.length), hit: true },
    { text: value.slice(at + needle.length), hit: false },
  ].filter((part) => part.text)
}
</script>
