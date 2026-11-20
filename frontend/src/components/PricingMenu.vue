<template>
  <button
    ref="trigger"
    type="button"
    class="cp-chip group max-w-full transition-colors"
    :class="[current ? current.tone : 'text-ink-gray-4 hover:bg-surface-gray-2', editable ? 'cursor-pointer' : 'cursor-default']"
    :title="current?.hint"
    @mousedown.stop
    @click.stop="editable && toggle()"
  >
    <span class="truncate">{{ label }}</span>
    <span v-if="editable" class="lucide-chevron-down size-3 shrink-0 opacity-50 group-hover:opacity-100" />
  </button>

  <Teleport to="body">
    <div
      v-if="open"
      ref="menu"
      class="fixed z-[2000] w-64 rounded-lg border border-outline-gray-2 bg-surface-base p-1 text-sm shadow-xl"
      :style="position"
      @mousedown.stop
      @pointerdown.stop
    >
      <div class="px-2 pb-1 pt-1.5 text-[13px] font-normal text-ink-gray-6">{{ title }}</div>
      <button
        v-for="option in options"
        :key="option.value"
        type="button"
        class="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-surface-gray-2"
        @click="pick(option.value)"
      >
        <span class="mt-1 size-2 shrink-0 rounded-full" :class="option.dot" />
        <span class="min-w-0 flex-1">
          <span class="block text-ink-gray-9">{{ option.label }}</span>
          <span class="block text-xs leading-snug text-ink-gray-5">{{ option.hint }}</span>
        </span>
        <span v-if="option.value === modelValue" class="lucide-check mt-0.5 size-3.5 shrink-0 text-ink-gray-8" />
      </button>
      <div v-if="modelValue === 'Cost plus' && markup !== undefined" class="mt-1 flex items-center gap-2 border-t border-outline-gray-1 px-2 pb-1 pt-2">
        <span class="flex-1 text-ink-gray-7">Markup</span>
        <input
          ref="markupInput"
          type="number"
          step="0.5"
          class="cp-input cp-sm w-20 text-right"
          :value="markup || ''"
          placeholder="0"
          @keydown.enter.prevent="saveMarkup($event.target.value); close()"
          @change="saveMarkup($event.target.value)"
        />
        <span class="text-ink-gray-5">%</span>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'

const props = defineProps({
  modelValue: String,
  options: { type: Array, required: true }, // [{ value, label, hint, tone, dot }]
  editable: Boolean,
  title: { type: String, default: 'Pricing' },
  placeholder: { type: String, default: 'Set…' },
  markup: { type: Number, default: undefined }, // given only for categories: edit it in the menu
})
const emit = defineEmits(['update:modelValue', 'update:markup'])

const trigger = ref(null)
const menu = ref(null)
const markupInput = ref(null)
const open = ref(false)
const position = ref({})

const current = computed(() => props.options.find((o) => o.value === props.modelValue))
const label = computed(() => {
  if (!current.value) return props.placeholder
  return current.value.label + (props.modelValue === 'Cost plus' && props.markup ? ` +${props.markup}%` : '')
})

function place() {
  const rect = trigger.value?.getBoundingClientRect()
  if (!rect) return
  const below = window.innerHeight - rect.bottom > 260
  position.value = below ? { left: rect.left + 'px', top: rect.bottom + 4 + 'px' } : { left: rect.left + 'px', bottom: window.innerHeight - rect.top + 4 + 'px' }
}

function onOutside(event) {
  if (!menu.value?.contains(event.target) && !trigger.value?.contains(event.target)) close()
}
function onKey(event) {
  if (event.key === 'Escape') close()
}

function toggle() {
  if (open.value) return close()
  place()
  open.value = true
  document.addEventListener('mousedown', onOutside, true)
  document.addEventListener('keydown', onKey, true)
  window.addEventListener('scroll', place, true)
}

function close() {
  open.value = false
  document.removeEventListener('mousedown', onOutside, true)
  document.removeEventListener('keydown', onKey, true)
  window.removeEventListener('scroll', place, true)
}
onBeforeUnmount(close)

async function pick(value) {
  if (value !== props.modelValue) emit('update:modelValue', value)
  if (value === 'Cost plus' && props.markup !== undefined) {
    await nextTick()
    markupInput.value?.focus()
    return
  }
  close()
}

function saveMarkup(raw) {
  const value = Number(raw) || 0
  if (value !== (props.markup || 0)) emit('update:markup', value)
}
</script>
