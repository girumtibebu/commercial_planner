<template>
  <div class="flex min-h-0 flex-1 flex-col overflow-y-auto">
    <div class="flex flex-1 flex-col gap-3.5 p-3.5 pb-6 sm:gap-4 sm:p-5">
      <div v-if="subtitle || $slots.actions" class="flex flex-wrap items-center justify-between gap-2.5 sm:gap-3">
        <p class="min-w-0 flex-1 truncate text-sm text-ink-gray-5">{{ subtitle }}</p>
        <div class="flex flex-wrap items-center gap-1.5 sm:gap-2"><slot name="actions" /></div>
      </div>
      <slot />
    </div>
  </div>
</template>

<script setup>
defineProps({ subtitle: String })
</script>
