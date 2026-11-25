<template>
  <div class="relative flex h-full w-full items-center">
    <input
      ref="input"
      v-model="text"
      class="h-full w-full border-0 bg-transparent p-0 !pr-5 text-[inherit] shadow-none outline-none focus:ring-0"
      autocomplete="off"
      @input="search"
      @keydown="onKey"
      @blur="onBlur"
    />
    <!-- tells you this field picks from a list -->
    <span class="pointer-events-none absolute right-0 size-3.5 text-ink-gray-5" :class="open ? 'lucide-chevron-up' : 'lucide-chevron-down'" />
    <Teleport to="body">
      <!-- pointerdown.stop: a Dialog must not treat a pick in this list as a click outside it -->
      <div
        v-if="open"
        class="fixed z-[2000] overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-base text-sm shadow-xl"
        :style="position"
        @mousedown.prevent
        @pointerdown.stop
      >
        <ul ref="list" class="max-h-64 overflow-auto py-1">
          <li
            v-for="(option, index) in choices"
            :key="option.kind + option.value"
            class="mx-1 cursor-pointer rounded-md px-2.5 py-1.5"
            :class="index === highlighted ? 'bg-surface-gray-2' : ''"
            @click="choose(option)"
            @mousemove="highlighted = index"
          >
            <template v-if="option.kind === 'text'">
              <div class="flex items-center gap-2 text-ink-gray-8">
                <span class="lucide-type size-3.5 text-ink-gray-5" />
                <span>Use “<span class="font-medium text-ink-gray-9">{{ option.value }}</span>” as text</span>
              </div>
              <div class="pl-[22px] text-xs text-ink-gray-5">No item link · the Default Service Item is used on RFQs and orders</div>
            </template>
            <template v-else>
              <div class="flex items-center gap-2">
                <div class="min-w-0 flex-1 font-medium text-ink-gray-9"><template v-for="(part, i) in marked(option.value)" :key="i"><b v-if="part.hit" class="text-ink-gray-9 underline decoration-ink-gray-4 underline-offset-2">{{ part.text }}</b><template v-else>{{ part.text }}</template></template></div>
                <span v-if="isCurrent(option)" class="lucide-check size-3.5 shrink-0 text-ink-gray-7" />
              </div>
              <div v-if="option.description" class="truncate text-xs text-ink-gray-5">{{ option.description }}</div>
            </template>
          </li>
          <li v-if="!choices.length" class="px-3 py-2 text-ink-gray-5">{{ loading ? 'Loading…' : 'No results found' }}</li>
        </ul>
        <div class="border-t border-outline-gray-1 p-1">
          <button class="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-ink-gray-7 hover:bg-surface-gray-2" @click="openDesk('new')">
            <span class="lucide-plus size-3.5" /> Create a new {{ doctype }}
          </button>
          <button class="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-ink-gray-7 hover:bg-surface-gray-2" @click="openDesk('list')">
            <span class="lucide-search size-3.5" /> Advanced search
          </button>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '../api'

/* A link editor (line items, UOM, suppliers…): the list opens as soon as the field is focused so it reads
   as a dropdown; typing filters it. Until you type or move through the list, Enter keeps the current value. */
const props = defineProps({
  doctype: String,
  initial: { type: String, default: '' },
  keepCaret: Boolean,
  /** Offer "Use … as text" so a name that is not a record can still be entered. */
  allowText: Boolean,
  /** Put that text option first (free-text lines); otherwise matching records come first. */
  preferText: Boolean,
  /** The editor was opened by a typed key: filter by it at once. */
  openOnStart: Boolean,
  /** The value's record name when it differs from the text shown (a line shows the item name, links the code). */
  current: { type: String, default: '' },
})
const emit = defineEmits(['commit', 'cancel'])

const input = ref(null)
const list = ref(null)
const text = ref(props.initial)
const options = ref([])
const highlighted = ref(-1)
const loading = ref(true)
const anchor = ref({ left: 0, top: 0, width: 280, up: false })
const done = ref(false)
const touched = ref(props.openOnStart) // typed or moved through the list: from then on Enter picks
let timer
let latest = 0

const open = computed(() => !done.value)
const typed = computed(() => text.value.trim())
const isCurrent = (option) => option.value === (props.current || props.initial)

/** Records from search, plus the typed text (once you type) when it is not already an exact record name. */
const choices = computed(() => {
  const records = options.value.map((option) => ({ ...option, kind: 'record' }))
  if (!props.allowText || !touched.value || !typed.value) return records
  if (records.some((option) => option.value.toLowerCase() === typed.value.toLowerCase())) return records
  const textChoice = { kind: 'text', value: typed.value }
  return props.preferText || !records.length ? [textChoice, ...records] : [...records, textChoice]
})

const position = computed(() => {
  const { left, top, width, up } = anchor.value
  return { left: left + 'px', minWidth: Math.max(width, 320) + 'px', ...(up ? { bottom: top + 'px' } : { top: top + 'px' }) }
})

/** Sit under the field, or above it when there is no room below (the footer needs ~290px). */
function placeList() {
  const rect = input.value?.getBoundingClientRect()
  if (!rect) return
  const up = window.innerHeight - rect.bottom < 290 && rect.top > window.innerHeight - rect.bottom
  anchor.value = { left: rect.left - 8, width: rect.width + 16, up, top: up ? window.innerHeight - rect.top + 6 : rect.bottom + 6 }
}

onMounted(async () => {
  await nextTick()
  input.value?.focus()
  if (props.keepCaret) input.value?.setSelectionRange(text.value.length, text.value.length)
  else input.value?.select()
  placeList()
  fetchOptions(touched.value ? text.value : '') // on focus: the whole list, not one filtered by the current value
  window.addEventListener('scroll', placeList, true)
  window.addEventListener('resize', placeList)
})

onBeforeUnmount(() => {
  clearTimeout(timer)
  window.removeEventListener('scroll', placeList, true)
  window.removeEventListener('resize', placeList)
})

watch(highlighted, async () => {
  await nextTick()
  if (highlighted.value >= 0) list.value?.children[highlighted.value]?.scrollIntoView({ block: 'nearest' })
})

async function fetchOptions(txt) {
  const ticket = ++latest
  loading.value = true
  const found = (await api.searchLink(props.doctype, txt)) || []
  if (ticket !== latest) return
  options.value = found
  // untouched: point at the current value (if listed); after typing: the best match
  highlighted.value = touched.value ? 0 : choices.value.findIndex(isCurrent)
  loading.value = false
  placeList()
}

function search() {
  touched.value = true
  highlighted.value = 0
  clearTimeout(timer)
  timer = setTimeout(() => fetchOptions(text.value), 120)
}

/** Split a result so the part you typed is marked, as in the Desk dropdown. */
function marked(value) {
  const needle = touched.value ? typed.value.toLowerCase() : ''
  const at = needle ? value.toLowerCase().indexOf(needle) : -1
  if (at < 0) return [{ text: value, hit: false }]
  return [
    { text: value.slice(0, at), hit: false },
    { text: value.slice(at, at + needle.length), hit: true },
    { text: value.slice(at + needle.length), hit: false },
  ].filter((part) => part.text)
}

function openDesk(where) {
  const slug = props.doctype.toLowerCase().replace(/ /g, '-')
  window.open(`/desk/${slug}${where === 'new' ? '/new' : ''}`, '_blank')
}

/** commit(value, isText): isText = the typed words, not a record name. */
function finish(kind, value, isText = false) {
  if (done.value) return
  done.value = true
  emit(kind, value, isText)
}

function choose(option) {
  if (option.kind === 'record' && isCurrent(option) && !touched.value) return finish('cancel') // same value: nothing to save
  finish('commit', option.value, option.kind === 'text')
}

function onKey(event) {
  const count = choices.value.length
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    event.stopPropagation()
    touched.value = true
    const step = event.key === 'ArrowDown' ? 1 : -1
    const from = highlighted.value < 0 ? (step > 0 ? -1 : 0) : highlighted.value
    highlighted.value = (from + step + count) % Math.max(count, 1)
  } else if (event.key === 'Enter' || event.key === 'Tab') {
    event.preventDefault()
    event.stopPropagation()
    if (!touched.value) return finish('cancel') // just looked: keep the value as it was
    if (!typed.value) return finish('commit', '')
    const picked = choices.value[highlighted.value]
    if (picked && (picked.kind === 'text' || !loading.value)) choose(picked)
  } else if (event.key === 'Escape') {
    event.stopPropagation()
    finish('cancel')
  } else {
    event.stopPropagation()
  }
}

function onBlur() {
  setTimeout(() => finish('cancel'), 150)
}
</script>
