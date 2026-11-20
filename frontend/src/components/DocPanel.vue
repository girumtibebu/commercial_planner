<template>
  <Teleport to="body">
    <div v-if="target" class="fixed inset-0 z-40" @keydown.esc="close">
      <div class="absolute inset-0 bg-black/10" @click="close" />
      <aside
        class="absolute inset-y-0 right-0 flex w-full max-w-[420px] flex-col border-l border-outline-gray-2 bg-surface-base shadow-2xl"
        role="dialog"
        :aria-label="`${target.doctype} ${target.name}`"
      >
        <header class="flex items-start gap-2 border-b border-outline-gray-1 px-4 py-3">
          <div class="min-w-0 flex-1">
            <div class="text-xs text-ink-gray-5">{{ target.doctype }}</div>
            <div class="truncate font-mono text-sm font-semibold text-ink-gray-9">{{ target.name }}</div>
            <div v-if="panel" class="mt-1 flex flex-wrap items-center gap-1.5">
              <Badge v-if="panel.workflow_state" :label="panel.workflow_state" size="sm" theme="blue" />
              <Badge v-if="panel.status && panel.status !== panel.workflow_state" :label="panel.status" size="sm" theme="gray" />
            </div>
          </div>
          <Button size="sm" variant="ghost" :link="deskPath(target.doctype, target.name)" title="Open the full form in Desk, in a new tab">
            <template #suffix><span class="lucide-external-link size-3.5" /></template>
            Open in desk
          </Button>
          <button class="flex h-7 w-7 items-center justify-center rounded text-ink-gray-5 hover:bg-surface-gray-2" title="Close (Esc)" @click="close">
            <span class="lucide-x size-4" />
          </button>
        </header>

        <div v-if="loading" class="p-4 text-sm text-ink-gray-5">Loading…</div>
        <div v-else-if="error" class="m-4 rounded-lg bg-surface-red-2 p-3 text-sm text-ink-red-8">{{ error }}</div>
        <div v-else-if="panel" class="flex-1 overflow-auto px-4 py-3 text-sm">
          <p v-if="panel.title && panel.title !== panel.name" class="mb-3 text-ink-gray-8">{{ panel.title }}</p>

          <div class="grid gap-3">
            <label v-for="field in panel.fields" :key="field.fieldname" class="grid gap-1">
              <span class="text-ink-gray-6">{{ field.label }}</span>
              <select v-if="field.fieldtype === 'Select'" v-model="form[field.fieldname]" class="cp-input" :disabled="!field.editable">
                <option v-for="o in (field.options || '').split('\n')" :key="o" :value="o">{{ o }}</option>
              </select>
              <textarea
                v-else-if="field.fieldtype === 'Small Text' || field.fieldtype === 'Text'"
                v-model="form[field.fieldname]"
                rows="3"
                class="cp-input"
                :disabled="!field.editable"
              />
              <input v-else-if="field.fieldtype === 'Check'" v-model="form[field.fieldname]" type="checkbox" :true-value="1" :false-value="0" :disabled="!field.editable" />
              <input
                v-else
                v-model="form[field.fieldname]"
                class="cp-input"
                :type="field.fieldtype === 'Date' ? 'date' : NUMBER.includes(field.fieldtype) ? 'number' : 'text'"
                :disabled="!field.editable"
              />
            </label>
          </div>

          <div v-if="panel.parties?.length" class="mt-4">
            <div class="mb-1 text-ink-gray-6">Suppliers</div>
            <div class="flex flex-wrap gap-1">
              <span v-for="p in panel.parties" :key="p" class="cp-chip bg-surface-gray-2 text-ink-gray-8">{{ p }}</span>
            </div>
          </div>

          <dl v-if="panel.totals" class="mt-4 grid grid-cols-2 gap-y-1 rounded-lg bg-surface-gray-1 px-3 py-2 tabular-nums">
            <dt class="text-ink-gray-6">Net total</dt>
            <dd class="text-right text-ink-gray-9">{{ money(panel.totals.net_total) }}</dd>
            <dt class="text-ink-gray-6">Grand total</dt>
            <dd class="text-right font-semibold text-ink-gray-9">{{ money(panel.totals.grand_total) }}</dd>
          </dl>
          <p class="mt-3 text-xs text-ink-gray-5">Items are edited in the cost plan grid. Everything else: Open in desk.</p>
        </div>

        <footer v-if="panel" class="flex flex-wrap items-center gap-2 border-t border-outline-gray-1 px-4 py-3">
          <Button v-if="dirty" variant="solid" :loading="busy" @click="save">Save</Button>
          <Button
            v-for="action in panel.actions"
            :key="action"
            :variant="dirty ? 'subtle' : action === panel.actions[0] ? 'solid' : 'subtle'"
            :theme="/reject|cancel/i.test(action) ? 'red' : 'gray'"
            :disabled="busy || dirty"
            :title="dirty ? 'Save your changes first' : ''"
            @click="run(action)"
          >
            {{ action }}
          </Button>
          <span v-if="!panel.actions.length && !dirty" class="text-xs text-ink-gray-5">No actions available to you now.</span>
        </footer>
      </aside>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { Badge, Button, toast } from 'frappe-ui'
import { api } from '../api'
import { readError } from '../useWorkspace'

const props = defineProps({ target: Object, deskPath: Function, fmt: Object })
const emit = defineEmits(['close', 'changed'])

const NUMBER = ['Float', 'Int', 'Currency', 'Percent']
const panel = ref(null)
const loading = ref(false)
const busy = ref(false)
const error = ref(null)
const form = reactive({})

const dirty = computed(() => Boolean(panel.value?.fields.some((f) => f.editable && (form[f.fieldname] ?? '') !== (f.value ?? ''))))
const money = (value) => (props.fmt ? props.fmt.money(value) : value)

function fill(data) {
  panel.value = data
  for (const key of Object.keys(form)) delete form[key]
  for (const field of data.fields) form[field.fieldname] = field.value
}

watch(
  () => props.target && `${props.target.doctype}/${props.target.name}`,
  async (key) => {
    panel.value = null
    error.value = null
    if (!key) return
    loading.value = true
    try {
      fill(await api.getPanel(props.target.doctype, props.target.name))
    } catch (err) {
      error.value = readError(err)
    } finally {
      loading.value = false
    }
  },
  { immediate: true },
)

async function save() {
  busy.value = true
  try {
    const values = Object.fromEntries(panel.value.fields.filter((f) => f.editable).map((f) => [f.fieldname, form[f.fieldname]]))
    fill(await api.savePanel(panel.value.doctype, panel.value.name, values, panel.value.modified))
    toast.success(`${panel.value.name} saved`)
    emit('changed')
  } catch (err) {
    toast.error(readError(err))
  } finally {
    busy.value = false
  }
}

async function run(action) {
  busy.value = true
  try {
    fill(await api.runPanelAction(panel.value.doctype, panel.value.name, action))
    toast.success(`${panel.value.name}: ${action}`)
    emit('changed') // a workflow step may lock or unlock the plan's version
  } catch (err) {
    toast.error(readError(err))
  } finally {
    busy.value = false
  }
}

function close() {
  if (dirty.value && !window.confirm('Discard your changes?')) return
  emit('close')
}
</script>
