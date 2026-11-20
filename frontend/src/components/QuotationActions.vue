<template>
  <div class="flex items-center gap-2">
    <span class="hidden text-xs text-ink-gray-5 md:inline">{{ saving ? 'Saving…' : savedLabel }}</span>
    <Button size="sm" :loading="flushing" :disabled="!focusVersion?.can_edit" title="Save (Ctrl+S). Edits are also saved as you type." @click="save">
      <template #prefix><span class="lucide-save size-3.5" /></template>
      Save
    </Button>
    <a
      v-if="state"
      class="hidden items-center gap-1.5 rounded-md px-2 py-1 text-xs text-ink-gray-6 hover:bg-surface-gray-2 lg:flex"
      :href="deskPath('Quotation', state.name)"
      target="_blank"
      :title="hint"
      @click.prevent="openPanel('Quotation', state.name)"
    >
      <span class="font-mono">{{ state.name }}</span>
      <Badge :label="state.syncing ? 'In sync' : state.status" size="sm" :theme="state.syncing ? 'green' : 'gray'" />
    </a>
  </div>
</template>

<script setup>
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Badge, Button, toast } from 'frappe-ui'
import { api } from '../api'

const { focusVersion, saving, flush, deskPath, openPanel } = inject('cp')

const state = ref(null)
const flushing = ref(false)
const savedAt = ref(null)

const savedLabel = computed(() => (savedAt.value ? `Saved ${savedAt.value}` : 'All changes saved'))
const hint = computed(() => {
  if (!state.value) return ''
  if (state.value.syncing) return 'Client lines and this draft Quotation are kept the same, both ways'
  if (state.value.docstatus === 2) return state.value.amended_to ? `Cancelled, amended to ${state.value.amended_to}` : 'Cancelled'
  if (state.value.docstatus === 0) return 'In review, or this version is locked: client lines do not sync'
  return `${state.value.status}: to change it, amend it in ERPNext; the plan follows with a new version`
})

async function refresh() {
  if (!focusVersion.value) return (state.value = null)
  try {
    state.value = await api.getQuotationState(focusVersion.value.name)
  } catch {
    state.value = null
  }
}
watch(() => [focusVersion.value?.name, focusVersion.value?.status, focusVersion.value?.syncs_quotation], refresh, { immediate: true })

async function save() {
  flushing.value = true
  try {
    await flush()
    savedAt.value = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    toast.success('All changes saved')
  } finally {
    flushing.value = false
  }
}

function onKey(event) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    event.preventDefault()
    save()
  }
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

defineExpose({ refresh })
</script>
