<template>
  <Dialog v-model="open" :options="{ title: 'Settings', size: '4xl' }">
    <template #body-content>
      <div v-if="!doc" class="py-10 text-center text-sm text-ink-gray-5">{{ loadError || 'Loading…' }}</div>
      <div v-else class="flex min-h-[420px] flex-col gap-4 text-sm sm:flex-row sm:gap-5">
        <nav class="flex shrink-0 gap-1 overflow-x-auto sm:w-44 sm:flex-col sm:gap-0.5" aria-label="Settings sections">
          <button
            v-for="tab in TABS"
            :key="tab.key"
            class="flex items-center gap-2 rounded-md px-2.5 py-1.5 text-left"
            :class="current === tab.key ? 'bg-surface-gray-3 font-medium text-ink-gray-9' : 'text-ink-gray-6 hover:bg-surface-gray-2'"
            :aria-current="current === tab.key ? 'page' : undefined"
            @click="current = tab.key"
          >
            <span :class="tab.icon" class="size-4" /> {{ tab.label }}
          </button>
        </nav>

        <div class="grid min-w-0 flex-1 content-start gap-4">
          <p v-if="!canWrite" class="rounded-lg bg-surface-gray-2 px-3 py-2 text-ink-gray-7">Read only: ask a Commercial Management user to change these.</p>

          <template v-if="current === 'general'">
            <div class="grid gap-4 sm:grid-cols-2">
              <Field hint="Owns the client job: vendor costs and the Sales Invoice go here.">
                <LinkField v-model="doc.lead_cost_center" label="Lead cost center" doctype="Cost Center" :disabled="!canWrite" />
              </Field>
              <Field hint="Used on RFQs and Purchase Orders for cost lines with no item.">
                <LinkField v-model="doc.default_service_item" label="Default service item" doctype="Item" :disabled="!canWrite" />
              </Field>
              <Field hint="Buying price list with the fixed (LTA) prices.">
                <LinkField v-model="doc.lta_price_list" label="LTA price list" doctype="Price List" :disabled="!canWrite" />
              </Field>
              <Field hint="Pre-fills Days on new lines when the plan has no event days.">
                <NumberField v-model="doc.default_event_days" label="Default event days" :disabled="!canWrite" />
              </Field>
              <Field hint="Debited on the lead cost center when a division's work is settled.">
                <LinkField v-model="doc.internal_charge_account" label="Internal charge account" doctype="Account" :disabled="!canWrite" />
              </Field>
              <Field hint="Credited on the division's cost center when its work is settled.">
                <LinkField v-model="doc.internal_income_account" label="Internal income account" doctype="Account" :disabled="!canWrite" />
              </Field>
            </div>
          </template>

          <template v-else-if="current === 'divisions'">
            <p class="text-ink-gray-6">Internal suppliers: work bought from them is settled between cost centers instead of paid.</p>
            <table class="w-full border-collapse">
              <thead>
                <tr class="border-b border-outline-gray-2 text-left text-ink-gray-6">
                  <th class="py-1.5 pr-2 font-normal">Division</th>
                  <th class="px-2 py-1.5 font-normal">Supplier</th>
                  <th class="px-2 py-1.5 font-normal">Cost center</th>
                  <th class="w-8" />
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, index) in doc.divisions" :key="row.name || index" class="border-b border-outline-gray-1 align-bottom">
                  <td class="py-1.5 pr-2"><input v-model="row.division_name" class="cp-input w-full" :disabled="!canWrite" aria-label="Division name" /></td>
                  <td class="px-2 py-1.5"><LinkField v-model="row.supplier" doctype="Supplier" :disabled="!canWrite" /></td>
                  <td class="px-2 py-1.5"><LinkField v-model="row.cost_center" doctype="Cost Center" :disabled="!canWrite" /></td>
                  <td class="py-1.5 text-right">
                    <button v-if="canWrite" class="rounded p-1 text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-red-6" title="Remove division" @click="doc.divisions.splice(index, 1)">
                      <span class="lucide-trash-2 size-3.5" />
                    </button>
                  </td>
                </tr>
                <tr v-if="!doc.divisions.length"><td colspan="4" class="py-4 text-center text-ink-gray-5">No divisions yet.</td></tr>
              </tbody>
            </table>
            <div v-if="canWrite"><Button size="sm" @click="doc.divisions.push({ division_name: '', supplier: '', cost_center: '' })">
              <template #prefix><span class="lucide-plus size-3.5" /></template>Add division
            </Button></div>
          </template>

          <template v-else-if="current === 'approval'">
            <p class="text-ink-gray-6">After winning, a budget revision needs approval when any check triggers against the Agreed budget. 0 turns a check off.</p>
            <div class="grid gap-4 sm:grid-cols-2">
              <Field hint="Client lines with an agreed cost at or above this are checked; a free extra at or above it needs approval.">
                <NumberField v-model="doc.line_threshold" label="Line threshold" :disabled="!canWrite" />
              </Field>
              <Field hint="Change, up or down, on those lines that needs approval.">
                <NumberField v-model="doc.line_change_pct" label="Line change %" :disabled="!canWrite" />
              </Field>
              <Field hint="Change of the job's total cost that needs approval.">
                <NumberField v-model="doc.job_change_pct" label="Job change %" :disabled="!canWrite" />
              </Field>
              <Field hint="Who approves revisions.">
                <LinkField v-model="doc.approver_role" label="Approver role" doctype="Role" :disabled="!canWrite" />
              </Field>
            </div>
          </template>

          <template v-else-if="current === 'workflow'">
            <label class="grid gap-1">
              <span class="text-ink-gray-6">Draft workflow states</span>
              <textarea v-model="doc.draft_workflow_states" rows="5" class="cp-input" :disabled="!canWrite" />
              <span class="text-xs text-ink-gray-5">One per line. While a Quotation or Sales Order is in one of these states its plan is editable; any other unsubmitted state locks it.</span>
            </label>
          </template>

          <p class="text-xs text-ink-gray-5">
            Planner columns are set in
            <a class="underline" :href="deskPath('Commercial Planning Settings', 'Commercial Planning Settings')" target="_blank">Desk</a>.
          </p>
        </div>
      </div>
    </template>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button label="Close" @click="open = false" />
        <Button v-if="canWrite" variant="solid" :loading="saving" :disabled="!doc" label="Save" @click="save" />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { h, inject, ref, watch } from 'vue'
import { Button, Dialog, call, toast } from 'frappe-ui'
import LinkField from './LinkField.vue'
import { readError } from '../useWorkspace'

const open = defineModel({ type: Boolean, default: false })
const { deskPath } = inject('cp')

const DOCTYPE = 'Commercial Planning Settings'
const TABS = [
  { key: 'general', label: 'General', icon: 'lucide-settings' },
  { key: 'divisions', label: 'Divisions', icon: 'lucide-building-2' },
  { key: 'approval', label: 'Budget approval', icon: 'lucide-badge-check' },
  { key: 'workflow', label: 'Workflow', icon: 'lucide-git-branch' },
]

const current = ref('general')
const doc = ref(null)
const canWrite = ref(false)
const saving = ref(false)
const loadError = ref(null)

watch(open, async (isOpen) => {
  if (!isOpen) return
  doc.value = null
  loadError.value = null
  try {
    const [settings, perm] = await Promise.all([
      call('frappe.client.get', { doctype: DOCTYPE, name: DOCTYPE }),
      call('frappe.client.has_permission', { doctype: DOCTYPE, docname: DOCTYPE, perm_type: 'write' }),
    ])
    doc.value = { ...settings, divisions: settings.divisions || [] }
    canWrite.value = Boolean(perm?.has_permission)
  } catch (err) {
    loadError.value = readError(err)
  }
})

async function save() {
  saving.value = true
  try {
    const saved = await call('frappe.client.save', { doc: JSON.stringify(doc.value) })
    doc.value = { ...saved, divisions: saved.divisions || [] }
    toast.success('Settings saved')
  } catch (err) {
    toast.error(readError(err))
  } finally {
    saving.value = false
  }
}

/** A field with its hint under it. */
const Field = (props, { slots }) => h('div', { class: 'grid gap-1' }, [slots.default?.(), h('span', { class: 'text-xs text-ink-gray-5' }, props.hint)])
Field.props = ['hint']

const NumberField = (props, { emit }) =>
  h('label', { class: 'grid gap-1 text-sm' }, [
    h('span', { class: 'text-ink-gray-6' }, props.label),
    h('input', {
      type: 'number',
      step: 'any',
      class: 'cp-input',
      value: props.modelValue ?? '',
      disabled: props.disabled,
      onInput: (event) => emit('update:modelValue', event.target.value === '' ? 0 : Number(event.target.value)),
    }),
  ])
NumberField.props = ['label', 'modelValue', 'disabled']
NumberField.emits = ['update:modelValue']
</script>
