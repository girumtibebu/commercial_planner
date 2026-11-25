<template>
  <div v-if="focus" class="grid gap-2 rounded-xl border border-outline-gray-2 bg-surface-base px-3 py-2 text-sm">
    <div class="flex flex-wrap items-center gap-2">
      <span class="text-ink-gray-6">{{ focus.can_edit ? 'Editing' : 'Viewing' }}</span>
      <span class="font-semibold text-ink-gray-9">V{{ focus.version_no }} {{ focus.version_name }}</span>
      <!-- locks follow the Quotation / Sales Order workflow and the revision approval: nobody locks a version by hand -->
      <span v-if="focus.status === 'Working'" class="cp-chip bg-surface-green-2 text-ink-green-8">
        {{ focus.is_revision ? 'Draft revision' : 'Editable' }}
      </span>
      <span v-else class="cp-chip" :class="LOCK_TONE[focus.lock_kind] || LOCK_TONE.Superseded">
        <span class="lucide-lock size-3" /> {{ focus.lock_reason || 'Locked' }}
      </span>
      <span v-if="focus.source_name" class="text-xs text-ink-gray-5">on {{ focus.source_doctype }} {{ focus.source_name }}</span>

      <div class="ml-auto flex items-center gap-2">
        <template v-if="focus.is_revision && focus.status === 'Working' && canWrite">
          <span class="hidden text-xs text-ink-gray-5 lg:inline">Small changes apply at once; large ones go to the approver.</span>
          <Button size="sm" variant="solid" :loading="busy" @click="run('submitRevision', focus.name)">
            <template #prefix><span class="lucide-send size-3.5" /></template>
            Submit revision
          </Button>
        </template>
        <template v-else-if="focus.can_approve">
          <Button size="sm" theme="red" variant="subtle" :disabled="busy" @click="rejectOpen = true">Reject</Button>
          <Button size="sm" variant="solid" :loading="busy" @click="run('approveRevision', focus.name)">
            <template #prefix><span class="lucide-check size-3.5" /></template>
            Approve
          </Button>
        </template>
        <template v-else-if="focus.status !== 'Working' && canWrite">
          <span class="hidden text-xs text-ink-gray-5 lg:inline">{{ won ? 'To change the budget, make a revision from it.' : 'To keep planning, make a new version from it.' }}</span>
          <Button size="sm" @click="$emit('new-version', focus.name)">
            <template #prefix><span class="lucide-copy-plus size-3.5" /></template>
            {{ won ? 'New revision' : 'New version from this' }}
          </Button>
        </template>
      </div>
    </div>

    <div v-if="focus.revision_status === 'Needs approval' && reasons.length" class="rounded-lg bg-surface-amber-1 px-3 py-2 text-xs text-ink-amber-8">
      <div class="mb-1 font-medium">Needs approval because:</div>
      <ul class="list-disc pl-4">
        <li v-for="reason in reasons" :key="reason">{{ reason }}</li>
      </ul>
    </div>
    <div v-else-if="focus.status === 'Working' && focus.reject_reason" class="rounded-lg bg-surface-red-1 px-3 py-2 text-xs text-ink-red-7">
      Rejected: {{ focus.reject_reason }}
    </div>

    <Dialog v-model="rejectOpen" :options="{ title: `Reject ${focus.version_name}`, size: 'md' }">
      <template #body-content>
        <label class="mb-1 block text-sm text-ink-gray-7">Why? The planner sees this on the revision.</label>
        <textarea v-model="reason" rows="3" class="cp-input w-full" />
        <div class="mt-4 flex justify-end gap-2">
          <Button label="Cancel" @click="rejectOpen = false" />
          <Button variant="solid" theme="red" label="Reject" :disabled="!reason.trim() || busy" @click="reject" />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { computed, inject, ref } from 'vue'
import { Button, Dialog, toast } from 'frappe-ui'
import { LOCK_TONE } from '../locks'

const props = defineProps({ focus: Object, canWrite: Boolean, won: Boolean })
defineEmits(['new-version'])

const { revisionAction } = inject('cp')
const busy = ref(false)
const rejectOpen = ref(false)
const reason = ref('')

const reasons = computed(() => {
  try {
    return JSON.parse(props.focus?.approval_reasons || '[]')
  } catch {
    return []
  }
})

const DONE = { Approved: 'Approved: it is now the Estimate', 'Needs approval': 'Sent to the approver', Draft: 'Back to draft' }

async function run(action, ...args) {
  busy.value = true
  const result = await revisionAction(action, ...args)
  busy.value = false
  if (result) toast.success(DONE[result.status] || 'Done')
  return result
}

async function reject() {
  const result = await run('rejectRevision', props.focus.name, reason.value)
  if (result) {
    rejectOpen.value = false
    reason.value = ''
  }
}
</script>
