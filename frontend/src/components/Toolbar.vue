<template>
  <div class="flex flex-wrap items-center gap-2 border-b border-outline-gray-2 bg-surface-base px-3 py-2">
    <template v-if="editable">
      <Button size="sm" @click="grid?.addLine()"><template #prefix><Icon name="plus" :size="12" /></template>Line</Button>
      <Button size="sm" @click="grid?.addCategory()"><template #prefix><Icon name="plus" :size="12" /></template>Category</Button>
      <span class="ml-1 hidden text-[11px] text-ink-gray-5 lg:inline">
        Click a cell to select, click again to edit · Enter saves · drag ⋮⋮ to reorder · Shift+Enter details
      </span>
    </template>
    <span v-else class="text-xs text-ink-gray-5">This version is locked. To keep planning, make a new version from it.</span>
    <ColumnPicker v-if="grid?.columns" :columns="grid.columns" class="ml-auto" />
    <Button
      v-if="actuals"
      size="sm"
      variant="ghost"
      :loading="refreshing"
      title="Re-read actual and committed cost from ERPNext (POs, invoices, settlements, project costs)"
      @click="$emit('refresh-actuals')"
    >
      <template #prefix><span class="lucide-refresh-cw size-3.5" /></template>
      Refresh actuals
    </Button>
  </div>
</template>

<script setup>
import { Button } from 'frappe-ui'
import ColumnPicker from './ColumnPicker.vue'
import Icon from './Icon.vue'

defineProps({ editable: Boolean, grid: Object, actuals: Boolean, refreshing: Boolean })
defineEmits(['refresh-actuals'])
</script>
