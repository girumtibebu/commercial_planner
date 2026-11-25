<template>
  <Dialog v-model="open" :options="{ title: 'New version', size: 'lg' }">
    <template #body-content>
      <div class="grid gap-3 text-sm">
        <p class="text-ink-gray-6">
          A copy you can edit. The version it comes from stays as it is, so the two can be compared. Rounds and the
          Agreed budget are saved automatically when documents are submitted; use this to keep planning after that.
        </p>

        <label class="grid gap-1">
          <span class="text-ink-gray-6">Copy from</span>
          <select v-model="from" class="cp-input">
            <option v-for="ver in ordered" :key="ver.name" :value="ver.name">
              V{{ ver.version_no }} {{ ver.version_name }}{{ ver.lock_reason ? ` · ${ver.lock_reason}` : '' }}
            </option>
          </select>
        </label>

        <label class="grid gap-1">
          <span class="text-ink-gray-6">Name</span>
          <input v-model="name" class="cp-input" placeholder="e.g. Re-sourced backdrop" />
        </label>

        <label class="flex items-start gap-2">
          <input v-model="apply" type="checkbox" class="mt-0.5" />
          <span>
            <span class="text-ink-gray-8">Bring in the changes from the document</span>
            <span class="block text-xs text-ink-gray-5">
              New items, quantity, unit and selling price are updated from {{ sourceName || 'the document' }}. Lines you edited keep your values.
            </span>
          </span>
        </label>

        <label class="grid gap-1">
          <span class="text-ink-gray-6">Reason <span class="text-ink-red-6">*</span></span>
          <textarea v-model="reason" rows="2" class="cp-input" placeholder="Why is this version needed?" />
        </label>

        <div class="mt-1 flex justify-end gap-2">
          <Button label="Cancel" @click="open = false" />
          <Button variant="solid" label="Create version" :disabled="!ready" :loading="busy" @click="submit" />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Button, Dialog } from 'frappe-ui'

const props = defineProps({
  modelValue: Boolean,
  versions: Array,
  defaultFrom: String,
  preset: String,
  applyChanges: Boolean,
})
const emit = defineEmits(['update:modelValue', 'create'])

const open = computed({ get: () => props.modelValue, set: (value) => emit('update:modelValue', value) })

const from = ref('')
const name = ref('')
const reason = ref('')
const busy = ref(false)
const apply = ref(false)
const ordered = computed(() => [...props.versions].sort((a, b) => b.version_no - a.version_no))
const source = computed(() => props.versions.find((ver) => ver.name === from.value))
const sourceName = computed(() => source.value?.source_name)
const ready = computed(() => from.value && name.value.trim() && reason.value.trim())

watch(open, (value) => {
  if (!value) return
  from.value = props.preset || props.defaultFrom || props.versions[props.versions.length - 1]?.name
  apply.value = props.applyChanges
  name.value = props.applyChanges && source.value ? `${source.value.version_name} (updated)` : ''
  reason.value = props.applyChanges && sourceName.value ? `${sourceName.value} changed` : ''
})

async function submit() {
  busy.value = true
  const created = await new Promise((resolve) =>
    emit('create', {
      from_version: from.value,
      version_name: name.value.trim(),
      reason: reason.value.trim(),
      apply_source_changes: apply.value ? 1 : 0,
      done: resolve,
    }),
  )
  busy.value = false
  if (created) open.value = false
}
</script>
