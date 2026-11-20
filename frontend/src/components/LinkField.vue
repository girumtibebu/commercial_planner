<template>
  <label class="grid gap-1 text-sm">
    <span class="text-ink-gray-6">{{ label }}</span>
    <div
      class="cp-input flex items-center"
      :class="editing ? '!border-outline-gray-4' : disabled ? 'cursor-not-allowed !bg-surface-gray-1' : 'cursor-pointer'"
      @click="start"
    >
      <LinkInput v-if="editing" :doctype="doctype" :initial="modelValue || ''" @commit="commit" @cancel="editing = false" />
      <template v-else>
        <span v-if="modelValue" class="flex-1 truncate text-ink-gray-9">{{ modelValue }}</span>
        <span v-else class="flex-1 text-ink-gray-4">{{ placeholder || 'Select…' }}</span>
        <button v-if="modelValue && !disabled" class="text-ink-gray-4 hover:text-ink-red-6" title="Clear" @click.stop="$emit('update:modelValue', '')">
          <Icon name="close" :size="11" />
        </button>
      </template>
    </div>
  </label>
</template>

<script setup>
import { ref } from 'vue'
import Icon from './Icon.vue'
import LinkInput from './LinkInput.vue'

const props = defineProps({ label: String, doctype: String, modelValue: String, placeholder: String, disabled: Boolean })
const emit = defineEmits(['update:modelValue'])

const editing = ref(false)

function start() {
  if (!props.disabled) editing.value = true
}

function commit(value) {
  editing.value = false
  emit('update:modelValue', value)
}
</script>
