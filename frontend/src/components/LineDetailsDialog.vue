<template>
  <Dialog v-model="open" :options="{ title: row ? row.description || 'Line details' : 'Line details', size: 'lg' }">
    <template #body-content>
      <div v-if="row" class="grid gap-3 text-sm">
        <label class="grid gap-1">
          <span class="text-ink-gray-6">Description</span>
          <input v-model="form.description" :disabled="!editable" class="cp-input" />
        </label>

        <div class="grid grid-cols-2 gap-3">
          <!-- the same field as the Pricing column and the Sourcing tab: changing it here shows there -->
          <label v-if="pricing" class="grid gap-1">
            <span class="text-ink-gray-6">{{ pricing.title }}</span>
            <select v-model="form[pricing.field]" :disabled="!editable" class="cp-input">
              <option value="" disabled>Choose…</option>
              <option v-for="o in pricing.options" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
            <span class="text-xs text-ink-gray-5">{{ pricingHint }}</span>
          </label>
          <LinkField v-model="form.cost_type" label="Cost type" doctype="Commercial Cost Type" :disabled="!editable" />
          <LinkField v-if="row.row_type !== 'Category'" v-model="form.item_code" label="ERPNext item" doctype="Item" :disabled="!editable" />
          <div v-if="row.row_type !== 'Category'" class="grid gap-1">
            <span class="text-ink-gray-6">Supplier</span>
            <div class="cp-input flex cursor-default items-center !bg-surface-gray-1 text-ink-gray-7" :title="supplierHint">
              <span class="truncate">{{ values.supplier || '—' }}</span>
            </div>
            <span class="text-xs text-ink-gray-5">{{ supplierHint }}</span>
          </div>
        </div>

        <label class="grid gap-1">
          <span class="text-ink-gray-6">Notes</span>
          <textarea v-model="form.notes" rows="3" :disabled="!editable" class="cp-input" placeholder="Assumptions, conditions, references…" />
        </label>

        <div class="mt-1 flex justify-end gap-2">
          <Button label="Close" @click="open = false" />
          <Button v-if="editable" variant="solid" label="Save details" :disabled="!dirty" @click="save" />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { computed, reactive, watch } from 'vue'
import { Button, Dialog } from 'frappe-ui'
import LinkField from './LinkField.vue'
import { pricingFor } from '../pricing'

const props = defineProps({ modelValue: Boolean, row: Object, version: String, editable: Boolean })
const emit = defineEmits(['update:modelValue', 'save'])

const open = computed({ get: () => props.modelValue, set: (value) => emit('update:modelValue', value) })
const FIELDS = ['description', 'cost_type', 'item_code', 'notes', 'pricing_basis']
const form = reactive(Object.fromEntries(FIELDS.map((field) => [field, ''])))
let original = {}

const values = computed(() => props.row?.values[props.version] || {})
const pricing = computed(() => (props.row ? pricingFor(props.row) : null))
const pricingHint = computed(() => pricing.value?.options.find((o) => o.value === form[pricing.value.field])?.hint || '')
const supplierHint = computed(() =>
  form.pricing_basis === 'Requirement' ? 'Set by the bid you pick in Sourcing' : 'Set in the Supplier column of the cost plan',
)

watch(
  () => [props.modelValue, props.row],
  () => {
    if (!props.modelValue || !props.row) return
    original = { description: props.row.description || '' }
    for (const field of FIELDS.slice(1)) original[field] = values.value[field] || ''
    Object.assign(form, original)
  },
  { immediate: true },
)

const changes = computed(() => FIELDS.filter((field) => (form[field] || '') !== (original[field] || '')))
const dirty = computed(() => changes.value.length > 0)

function save() {
  const update = Object.fromEntries(changes.value.map((field) => [field, form[field] || null]))
  emit('save', { row_key: props.row.row_key, values: update })
  open.value = false
}
</script>
