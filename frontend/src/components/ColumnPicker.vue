<template>
  <Popover placement="bottom-end">
    <template #target="{ togglePopover }">
      <Button size="sm" variant="ghost" title="Choose columns" @click="togglePopover()">
        <template #prefix><span class="lucide-settings-2 size-3.5" /></template>
        Columns
      </Button>
    </template>
    <template #body>
      <div class="mt-1 w-72 rounded-lg border border-outline-gray-2 bg-surface-base p-2 text-sm shadow-xl">
        <div class="mb-2 flex flex-wrap gap-1">
          <button
            v-for="name in Object.keys(columns.views)"
            :key="name"
            class="rounded-md bg-surface-gray-2 px-2 py-1 text-xs text-ink-gray-8 hover:bg-surface-gray-3"
            @click="columns.applyView(name)"
          >
            {{ name }}
          </button>
        </div>
        <p class="mb-1 px-1 text-xs text-ink-gray-5">Tick to show · drag to reorder · saved for you on every device</p>
        <ul class="max-h-80 overflow-auto">
          <li
            v-for="col in ordered"
            :key="col.key"
            class="flex items-center gap-2 rounded px-1 py-1 hover:bg-surface-gray-1"
            :class="{ 'bg-surface-gray-2': dragKey === col.key }"
            :draggable="isShown(col.key) && col.key !== 'description'"
            @dragstart="dragKey = col.key"
            @dragover.prevent
            @drop.prevent="dropOn(col.key)"
            @dragend="dragKey = null"
          >
            <span class="lucide-grip-vertical size-3.5" :class="isShown(col.key) && col.key !== 'description' ? 'cursor-grab text-ink-gray-4' : 'invisible'" />
            <input
              :id="'cp-col-' + col.key"
              type="checkbox"
              :checked="isShown(col.key)"
              :disabled="col.key === 'description' || columns.fixed.includes(col.key)"
              :title="columns.fixed.includes(col.key) ? 'Always shown' : ''"
              @change="toggle(col.key)"
            />
            <label :for="'cp-col-' + col.key" class="flex-1 cursor-pointer text-ink-gray-8">{{ col.label }}</label>
            <span v-if="col.applies_to !== 'Both'" class="text-[11px] text-ink-gray-5">{{ col.applies_to === 'Client lines' ? 'client' : 'cost' }}</span>
          </li>
        </ul>
      </div>
    </template>
  </Popover>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Button, Popover } from 'frappe-ui'

const props = defineProps({ columns: { type: Object, required: true } })

const dragKey = ref(null)
const shownKeys = computed(() => props.columns.chosen.value.map((col) => col.key))
const isShown = (key) => shownKeys.value.includes(key)

/** Shown columns first, in their order, then the rest in the admin's order. */
const ordered = computed(() => {
  const all = props.columns.available.value
  const shown = props.columns.chosen.value.map((col) => all.find((a) => a.key === col.key)).filter(Boolean)
  return [...shown, ...all.filter((col) => !isShown(col.key))]
})

function toggle(key) {
  if (props.columns.fixed.includes(key)) return // always shown
  const current = props.columns.chosen.value
  props.columns.setChoice(isShown(key) ? current.filter((col) => col.key !== key) : [...current, { key }])
}

function dropOn(targetKey) {
  const moving = dragKey.value
  dragKey.value = null
  if (!moving || moving === targetKey || !isShown(targetKey) || targetKey === 'description') return
  const list = props.columns.chosen.value.filter((col) => col.key !== moving)
  const at = list.findIndex((col) => col.key === targetKey)
  list.splice(at, 0, props.columns.chosen.value.find((col) => col.key === moving))
  props.columns.setChoice(list)
}
</script>
