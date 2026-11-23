<template>
  <div
    ref="gridEl"
    class="sheet relative h-full overflow-auto bg-surface-base text-sm text-ink-gray-8 outline-none"
    tabindex="0"
    @keydown="onGridKey"
    @mouseleave="hoverKey = null"
  >
    <div class="grid w-max min-w-full" :style="{ gridTemplateColumns }">
      <!-- group bands -->
      <div
        v-for="(group, index) in groups"
        :key="'g' + index"
        class="sheet-head sticky top-0 z-10 flex h-7 items-center px-3 text-[12px] font-medium"
        :class="[group.tone, index === 0 ? 'sheet-frozen z-20' : '']"
        :style="{ gridColumn: `span ${group.span}` }"
      >
        {{ group.label }}
      </div>

      <!-- column headers -->
      <div
        v-for="(col, index) in cols"
        :key="'h' + col.key"
        class="sheet-head sticky z-10 flex h-8 items-center gap-1.5 bg-surface-gray-1 px-3 text-[13px] font-normal text-ink-gray-6"
        :class="[ALIGN[col.align], index === 0 ? 'sheet-frozen z-20' : '']"
        :style="{ top: '28px' }"
      >
        <template v-if="col.version && !col.single">
          <span :class="col.version === focusName ? 'font-semibold text-ink-gray-9' : ''">{{ col.label }}</span>
          <span v-if="col.role" class="cp-chip bg-surface-gray-2 text-ink-gray-7">{{ col.role }}</span>
        </template>
        <template v-else>{{ col.label }}</template>
        <span
          v-if="col.key !== 'actions'"
          class="col-resize"
          title="Drag to resize · double-click to reset"
          @mousedown.stop.prevent="startResize($event, col)"
          @dblclick.stop="resetWidth(col)"
        />
      </div>

      <!-- rows -->
      <template v-for="row in rows" :key="row.row_key">
        <div
          v-if="row.row_key === dividerKey"
          class="sheet-cell sticky left-0 border-t-2 border-outline-gray-3 bg-surface-gray-1 text-xs font-medium uppercase tracking-wide text-ink-gray-6"
          :style="{ gridColumn: '1 / -1' }"
          title="Not part of what the client signed: free extras, or billed as a variation"
        >
          Added after agreement
        </div>
        <div
          v-if="!row.parent_key && ws.sections?.[row.row_key]"
          class="sheet-cell sticky left-0 flex items-center gap-2 border-t-2 border-outline-gray-3 bg-surface-gray-1 font-semibold text-ink-gray-9"
          :style="{ gridColumn: '1 / -1' }"
          title="A section of the Quotation (edit it there)"
        >
          <span class="cp-chip border border-outline-gray-3 text-ink-gray-6">Section</span>
          {{ ws.sections[row.row_key] }}
        </div>
        <div
          v-for="(col, index) in cols"
          :key="row.row_key + col.key"
          :data-cell="row.row_key + ':' + col.key"
          class="sheet-cell"
          :class="cellClasses(row, col, index)"
          @mousedown="col.key !== 'actions' && onCellMouseDown(row, col, $event)"
          @mouseenter="hoverKey = row.row_key"
          @dragover="onDragOver(row, $event)"
          @drop="onDrop(row, $event)"
        >
          <template v-if="col.key === 'actions'">
            <div v-if="canEdit" class="flex items-center gap-0.5 opacity-0 group-hover:opacity-100" :class="{ '!opacity-100': hoverKey === row.row_key || active.key === row.row_key }">
              <Dropdown :options="rowMenu(row)" placement="right">
                <button class="flex h-6 w-6 items-center justify-center rounded text-ink-gray-5 hover:bg-surface-gray-3" title="Row actions">
                  <Icon name="dots" :size="14" />
                </button>
              </Dropdown>
              <button class="flex h-6 w-6 items-center justify-center rounded text-ink-gray-5 hover:bg-surface-red-2 hover:text-ink-red-6" title="Delete row" @click="act(row, remove)">
                <Icon name="close" :size="12" />
              </button>
            </div>
          </template>

          <template v-else-if="isEditing(row, col)">
            <LinkInput
              v-if="typeOf(row, col) === 'link'"
              :doctype="doctypeOf(row, col)"
              :initial="draft"
              :keep-caret="typedStart"
              :open-on-start="typedKey"
              :current="col.key === 'description' ? valuesIn(row, focusName)?.item_code || '' : ''"
              :allow-text="col.key === 'description'"
              :prefer-text="col.key === 'description' && row.row_type !== 'Category'"
              @commit="(value, isText) => commitLink(row, col, value, isText)"
              @cancel="cancelEdit"
            />
            <input
              v-else
              ref="editor"
              v-model="draft"
              :inputmode="col.type === 'number' ? 'decimal' : 'text'"
              @keydown="onEditKey($event, row, col)"
              @blur="onEditBlur(row, col)"
            />
          </template>

          <template v-else-if="index === 0">
            <span
              v-if="canEdit"
              class="drag-grip -ml-2 mr-0.5 flex h-6 w-4 shrink-0 cursor-grab items-center justify-center rounded text-ink-gray-4 hover:bg-surface-gray-3 hover:text-ink-gray-7 active:cursor-grabbing"
              :class="{ 'is-visible': hoverKey === row.row_key || dragKey === row.row_key }"
              draggable="true"
              :title="row.row_type === 'Category' ? 'Drag to reorder categories (its lines move with it)' : 'Drag to reorder within this category'"
              @mousedown.stop
              @dragstart="onDragStart(row, $event)"
              @dragend="onDragEnd"
            >
              <span class="lucide-grip-vertical size-3.5" />
            </span>
            <span
              class="mr-1 flex h-5 w-5 shrink-0 cursor-pointer select-none items-center justify-center rounded text-ink-gray-5 hover:bg-surface-gray-3"
              :style="{ marginLeft: row.depth * 18 + 'px' }"
              @mousedown.stop.prevent="row.hasChildren && toggle(row.row_key)"
            >
              <Icon v-if="row.hasChildren" :name="collapsed.has(row.row_key) ? 'chevright' : 'chevdown'" :size="12" />
            </span>
            <span v-if="!row.description" class="truncate italic text-ink-gray-4">
              {{ row.row_type === 'Category' ? 'Untitled category' : 'New cost line' }}
            </span>
            <span v-else class="truncate">{{ row.description }}</span>
            <span
              v-if="valuesIn(row, focusName)?.cost_type && row.row_type !== 'Category'"
              class="ml-2 shrink-0 rounded-full bg-surface-gray-2 px-2 py-px text-[10px] font-medium text-ink-gray-6"
            >{{ valuesIn(row, focusName).cost_type }}</span>
            <span v-if="valuesIn(row, focusName)?.supplier" class="ml-2 truncate text-xs text-ink-gray-5">{{ valuesIn(row, focusName).supplier }}</span>
            <button
              v-if="isQuoteLine(row)"
              class="cp-chip ml-2 shrink-0 hover:opacity-80"
              :class="sourcingChip(row).tone"
              title="Open in Sourcing"
              @mousedown.stop.prevent="router.push({ name: 'sourcing', params: { plan: ws.plan.name }, query: { line: row.row_key } })"
            >{{ sourcingChip(row).label }}</button>
            <Icon v-if="valuesIn(row, focusName)?.notes" name="message" :size="11" class="ml-2 shrink-0 text-ink-gray-4" :title="valuesIn(row, focusName).notes" />
            <a
              v-if="anyValue(row, 'variation_order')"
              class="cp-chip ml-2 shrink-0 cursor-pointer"
              :class="variationAgreed(row) ? 'bg-surface-violet-2 text-ink-violet-7' : 'bg-surface-amber-2 text-ink-amber-8'"
              :title="variationAgreed(row) ? 'Agreed with the client: counts in Agreed budget and price' : 'Draft variation: not agreed yet'"
              @mousedown.stop.prevent="openPanel('Sales Order', anyValue(row, 'variation_order'))"
            >{{ variationAgreed(row) ? 'variation' : 'variation draft' }} {{ anyValue(row, 'variation_order') }}</a>
            <span v-else-if="anyValue(row, 'after_agreement') && !row.parent_key" class="cp-chip ml-2 shrink-0 bg-surface-gray-2 text-ink-gray-7" title="Added after agreement; the client does not pay for it unless you bill it">free extra</span>
            <span v-if="valuesIn(row, focusName)?.off_quotation" class="cp-chip ml-2 shrink-0 bg-surface-gray-3 text-ink-gray-7" title="Its item was removed from the Quotation. The cost work is kept until you delete the line or the item returns.">not on quotation</span>
            <span v-else-if="valuesIn(row, focusName)?.changed_in_quotation" class="cp-chip ml-2 shrink-0 bg-surface-blue-2 text-ink-blue-8" title="Changed in the Quotation in Desk">updated in Quotation</span>
            <span
              v-if="changeFlag(row)"
              class="cp-chip ml-2 shrink-0"
              :class="changeFlag(row) === 'new' ? 'bg-surface-green-2 text-ink-green-8' : 'bg-surface-amber-2 text-ink-amber-8'"
            >{{ changeFlag(row) }}</span>
          </template>

          <template v-else-if="col.key === 'basis'">
            <PricingMenu
              v-if="pricingFor(row) && valuesIn(row, focusName)"
              :model-value="valuesIn(row, focusName)[pricingFor(row).field]"
              :options="pricingFor(row).options"
              :title="pricingFor(row).title"
              placeholder="Set source…"
              :editable="canEdit"
              @update:model-value="(value) => setValues(row, { [pricingFor(row).field]: value })"
            />
          </template>

          <template v-else>
            <span class="truncate" :title="lockedHint(row, col)">{{ display(row, col) }}</span>
          </template>
        </div>
      </template>

      <!-- totals -->
      <div
        v-for="(col, index) in cols"
        :key="'t' + col.key"
        class="sheet-head sticky bottom-0 z-10 flex h-9 items-center border-t border-outline-gray-2 bg-surface-gray-1 px-3 text-sm font-semibold text-ink-gray-9"
        :class="[ALIGN[col.align], index === 0 ? 'sheet-frozen z-20' : '', totalTone(col)]"
      >
        {{ totalFor(col) }}
      </div>
    </div>

    <div v-if="!rows.length" class="flex flex-col items-center gap-2 p-10 text-center text-ink-gray-5">
      <span>{{ filtering ? 'No rows match the filter.' : 'No rows yet.' }}</span>
      <Button v-if="canEdit && !filtering" size="sm" @click="addCategory">Add a category to start planning</Button>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Button, Dropdown, toast } from 'frappe-ui'
import { useRouter } from 'vue-router'
import Icon from './Icon.vue'
import LinkInput from './LinkInput.vue'
import PricingMenu from './PricingMenu.vue'
import { api } from '../api'
import { pricingFor } from '../pricing'
import { VIEWS } from '../columns'
import { parseNumber } from '../format'
import { indexRows, moveOp, visibleRows } from '../tree'

const props = defineProps({
  ws: { type: Object, required: true },
  focus: { type: Object, default: null },
  fmt: { type: Object, required: true },
  send: { type: Function, required: true },
  setItemField: { type: Function, default: () => {} },
  search: { type: String, default: '' },
  costType: { type: String, default: '' },
})
const emit = defineEmits(['details'])
const { openPanel, revisionAction } = inject('cp')
const router = useRouter()

const gridEl = ref(null)
const editor = ref(null)
const collapsed = ref(new Set())
const active = ref({ key: null, col: 'description' })
const editing = ref(false)
const draft = ref('')
const typedStart = ref(false)
const typedKey = ref(false) // editor opened by typing a character (not by click/Enter)
const hoverKey = ref(null)

const filtering = computed(() => Boolean(props.search || props.costType))
const focusName = computed(() => props.focus?.name)
const canEdit = computed(() => Boolean(props.focus?.can_edit))

/* ------------------------------------------------------------------ columns */
const BANDS = {
  line: { label: 'Plan line', tone: 'bg-surface-base text-ink-gray-6' },
  sourcing: { label: 'Sourcing', tone: 'bg-surface-base text-ink-gray-6' },
  cost: { label: 'Internal cost', tone: 'bg-surface-amber-2 text-ink-amber-8' },
  selling: { label: 'Client selling', tone: 'bg-surface-blue-2 text-ink-blue-8' },
  result: { label: 'Result', tone: 'bg-surface-green-2 text-ink-green-8' },
  none: { label: '', tone: 'bg-surface-base' },
}

/* Columns: the admin's list (Settings) says what can appear; each user's choice (order, widths) is saved
   on the server, so it follows them across devices. Three ready views fill the choice in one click. */
const MIN_WIDTH = 56

/** The price and result columns are always shown: no user can hide them, and a saved choice or view cannot drop them. */
const FIXED_COLUMNS = ['unit_cost', 'rate', 'cost', 'selling', 'profit', 'margin']
const available = computed(() => props.ws.grid_columns?.available || [])
const choice = ref(null) // [{ key, width? }] or null = the admin's defaults
watch(() => props.ws.grid_columns?.chosen, (saved) => { if (choice.value == null && saved) choice.value = saved }, { immediate: true })

const chosen = computed(() => {
  const known = new Map(available.value.map((col) => [col.key, col]))
  const list = choice.value || available.value.filter((col) => col.shown).map((col) => ({ key: col.key }))
  const picked = list.filter((entry) => known.has(entry.key))
  if (!picked.some((entry) => entry.key === 'description')) picked.unshift({ key: 'description' })
  for (const key of FIXED_COLUMNS) if (known.has(key) && !picked.some((entry) => entry.key === key)) picked.push({ key })
  return picked.map((entry) => ({ ...known.get(entry.key), width: entry.width || known.get(entry.key).width }))
})

let saveTimer = null
function setChoice(list) {
  choice.value = list.map((col) => (col.width ? { key: col.key, width: col.width } : { key: col.key }))
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => api.saveColumns(choice.value).catch(() => toast.error('Could not save your columns')), 600)
}

function applyView(name) {
  const keys = VIEWS[name].filter((key) => available.value.some((col) => col.key === key))
  setChoice(keys.map((key) => ({ key })))
}

function startResize(event, col) {
  const startX = event.clientX
  const startWidth = col.width
  const key = col.choiceKey
  document.body.style.cursor = 'col-resize'
  let width = startWidth
  const move = (e) => {
    width = Math.max(MIN_WIDTH, Math.round(startWidth + e.clientX - startX))
    liveWidths.value = { ...liveWidths.value, [col.key]: width }
  }
  const up = () => {
    window.removeEventListener('mousemove', move)
    window.removeEventListener('mouseup', up)
    document.body.style.cursor = ''
    setChoice(chosen.value.map((c) => (c.key === key ? { ...c, width } : c)))
    liveWidths.value = {}
  }
  window.addEventListener('mousemove', move)
  window.addEventListener('mouseup', up)
}

function resetWidth(col) {
  const admin = available.value.find((c) => c.key === col.choiceKey)
  setChoice(chosen.value.map((c) => (c.key === col.choiceKey ? { key: c.key, width: admin?.width } : c)))
}

const liveWidths = ref({}) // while dragging, before the choice is saved
// On a phone the description takes less room, so the numbers beside it are visible as the grid scrolls sideways
const phone = ref(window.matchMedia('(max-width: 767px)').matches)
const phoneQuery = window.matchMedia('(max-width: 767px)')
const onPhone = (event) => (phone.value = event.matches)
phoneQuery.addEventListener('change', onPhone)
onBeforeUnmount(() => phoneQuery.removeEventListener('change', onPhone))
const cols = computed(() =>
  baseCols.value.map((col) => ({ ...col, width: liveWidths.value[col.key] ?? (phone.value && col.key === 'description' ? 200 : col.width) })),
)

/** One chosen column becomes one grid column (or, for "cost", one per version on screen). */
function expand(col) {
  const versions = props.ws.columns
  const base = { choiceKey: col.key, label: col.label, width: col.width, applies: col.applies_to, align: 'center', type: 'readonly' }
  const field = (key, extra) => ({ ...base, key, field: key, type: 'number', number: true, ...extra })
  switch (col.key) {
    case 'description': return [{ ...base, key: 'description', type: 'text', align: 'left', band: 'line' }]
    case 'basis': return [{ ...base, key: 'basis', band: 'sourcing' }]
    case 'qty': return [field('qty', { band: 'line' })]
    case 'days': return [field('days', { band: 'line' })]
    case 'pages': return [field('pages', { band: 'line' })]
    case 'uom': return [{ ...base, key: 'uom', field: 'uom', type: 'link', doctype: 'UOM', band: 'line' }]
    case 'rate': return [field('rate', { align: 'right', band: 'selling' })]
    case 'unit_cost': return [field('unit_cost', { align: 'right', band: 'cost' })]
    case 'cost':
      // one version on screen: it is named on the version bar, so the column is just the line's cost (qty × days × unit cost)
      return versions.map((column) => ({
        ...base, key: 'cost:' + column.version, label: versions.length > 1 ? column.short : col.label,
        version: column.version, single: versions.length === 1, number: true, align: 'right', band: 'cost',
      }))
    case 'delta':
      return versions.length > 1 ? [{ ...base, key: 'delta', label: `vs ${versions[0].short}`, number: true, align: 'right', band: 'cost' }] : []
    case 'supplier': return [{ ...base, key: 'supplier', field: 'supplier', type: 'link', doctype: 'Supplier', align: 'left', band: 'sourcing' }]
    case 'ordered': return [{ ...base, key: 'committed', number: true, align: 'right', band: 'cost' }]
    case 'spent': return [{ ...base, key: 'actual', number: true, align: 'right', band: 'cost' }]
    case 'left': return [{ ...base, key: 'left', number: true, align: 'right', band: 'cost' }]
    case 'selling': return [{ ...base, key: 'selling', number: true, align: 'right', band: 'selling' }]
    case 'profit': return [{ ...base, key: 'profit', number: true, align: 'right', band: 'result' }]
    case 'margin': return [{ ...base, key: 'margin', number: true, band: 'result' }]
    default: // a Quotation Item field from Settings
      return [{ ...base, key: 'item:' + col.key, itemField: col.key, type: col.editable ? 'text' : 'readonly', band: 'selling' }]
  }
}

// Columns keep the user's order within a band; bands keep this order so each band header shows once.
const BAND_ORDER = ['line', 'sourcing', 'cost', 'selling', 'result']
const baseCols = computed(() => [
  ...chosen.value.flatMap(expand).sort((a, b) => BAND_ORDER.indexOf(a.band) - BAND_ORDER.indexOf(b.band)),
  { key: 'actions', label: '', width: 64, type: 'readonly', align: 'center', band: 'none' },
])

/** Totals of recorded cost by basis (lines rolled up to their categories, plus unallocated project costs). */
const recorded = computed(() => {
  const actuals = props.ws.actuals
  const totals = { Actual: 0, Committed: 0 }
  for (const [key, bucket] of Object.entries(actuals.rows)) {
    if (props.ws.rows.find((row) => row.row_key === key)?.parent_key) continue // counted in its category
    totals.Actual += bucket.Actual || 0
    totals.Committed += bucket.Committed || 0
  }
  totals.Actual += actuals.unallocated.Actual || 0
  totals.Committed += actuals.unallocated.Committed || 0
  return totals
})

const ALIGN = { left: 'justify-start text-left', center: 'justify-center text-center', right: 'justify-end text-right' }

const groups = computed(() => {
  const merged = []
  for (const col of baseCols.value) {
    const last = merged[merged.length - 1]
    if (last && last.band === col.band) last.span += 1
    else merged.push({ band: col.band, span: 1 })
  }
  return merged.map((group) => ({ ...group, label: BANDS[group.band].label, tone: BANDS[group.band].tone }))
})

// Every column keeps the width you set; spare room goes to the empty actions column.
const gridTemplateColumns = computed(() =>
  cols.value.map((col) => (col.key === 'actions' ? `minmax(${col.width}px, 1fr)` : col.width + 'px')).join(' '),
)

/* --------------------------------------------------------------------- rows */
const index = computed(() => indexRows(props.ws.rows))

function matchText(row, search, costType) {
  const holders = Object.values(row.values)
  if (costType && !holders.some((v) => v.cost_type === costType)) return false
  if (!search) return true
  const needle = search.toLowerCase()
  const haystack = [row.description, ...holders.flatMap((v) => [v.supplier, v.item_code, v.cost_type, v.notes])]
  return haystack.some((text) => text && String(text).toLowerCase().includes(needle))
}

const rows = computed(() =>
  visibleRows(props.ws.rows, { collapsed: collapsed.value, search: props.search, costType: props.costType, matchText }),
)

const activeRow = computed(() => index.value.byKey.get(active.value.key) || null)

function toggle(key) {
  const next = new Set(collapsed.value)
  next.has(key) ? next.delete(key) : next.add(key)
  collapsed.value = next
}


/* ------------------------------------------------------------------ values */
const latestVersion = computed(() => props.ws.columns[props.ws.columns.length - 1]?.version)

const valuesIn = (row, version) => row.values[version] || null

function fieldFor(row, col) {
  if (col.key === 'basis') return 'pricing_basis'
  if (col.field === 'unit_cost' && row.row_type === 'Adjustment' && valuesIn(row, focusName.value)?.adj_mode !== 'Fixed') {
    return 'adj_percent'
  }
  return col.field
}

/* ------------------------------------------------------------- pricing */
/** Cost-from menu changes: applied on screen at once, then saved. */
function setValues(row, values) {
  const own = valuesIn(index.value.byKey.get(row.row_key) || row, focusName.value)
  if (own) Object.assign(own, values)
  props.send(focusName.value, [{ op: 'update', row_key: row.row_key, values }])
}

const isQuoteLine = (row) => row.row_type === 'Cost Item' && valuesIn(row, focusName.value)?.pricing_basis === 'Requirement'
/** Where a Quote (RFQ) line stands in Sourcing, from its own links. */
function sourcingChip(row) {
  const own = valuesIn(row, focusName.value) || {}
  if (own.purchase_order) return { label: `PO ${own.purchase_order.replace(/^.*-(\d+)$/, '#$1')}`, tone: 'bg-surface-gray-3 text-ink-gray-8' }
  if (own.supplier_quotation) return { label: `bid: ${own.supplier}`, tone: 'bg-surface-green-2 text-ink-green-8' }
  if (own.rfq) return { label: 'RFQ sent', tone: 'bg-surface-blue-2 text-ink-blue-8' }
  return { label: 'to quote', tone: 'bg-surface-amber-2 text-ink-amber-8' }
}
const isLtaLine = (row) => row.row_type === 'Cost Item' && valuesIn(row, focusName.value)?.pricing_basis === 'LTA'

/** The first client line added after agreement: the divider goes above it. */
const anyValue = (row, field) => Object.values(row.values).find((v) => v?.[field])?.[field] || null
const dividerKey = computed(() => rows.value.find((row) => !row.parent_key && anyValue(row, 'after_agreement'))?.row_key || null)
const variationAgreed = (row) => props.ws.summary?.variations?.[anyValue(row, 'variation_order')]?.docstatus === 1

const isClientLine = (row) => row.row_type === 'Category' && !row.parent_key
const CLIENT_COLS = ['description', 'qty', 'days', 'pages', 'rate']

/** A column for client lines only (or cost lines only) stays blank on the other kind of row. */
function applies(row, col) {
  if (col.applies === 'Client lines') return isClientLine(row)
  if (col.applies === 'Cost lines') return row.row_type !== 'Category'
  return true
}

/** Client fields of a linked client line belong to the document: editable while the draft Quotation syncs. */
const clientEditable = (row) => !props.focus?.syncs_quotation && !valuesIn(row, focusName.value)?.linked

function lockedHint(row, col) {
  if (col.key === 'unit_cost' && isQuoteLine(row)) return 'Priced from the RFQ: pick a supplier quote in Sourcing'
  if (col.key === 'unit_cost' && isLtaLine(row)) {
    return valuesIn(row, focusName.value)?.cost_source === 'LTA Price' ? 'From the LTA price list' : 'No LTA price for this item (and supplier) yet'
  }
  if (col.key === 'supplier' && isQuoteLine(row)) return 'Set by the bid you pick in Sourcing'
  if (isClientLine(row) && CLIENT_COLS.includes(col.key) && canEdit.value && !clientEditable(row)) {
    return `Follows ${props.focus?.source_doctype} ${props.focus?.source_name}: change it there`
  }
  return undefined
}

function rawValue(row, col) {
  if (col.key === 'description') return row.description
  if (col.itemField) return valuesIn(row, focusName.value)?.item?.[col.itemField]
  return valuesIn(row, focusName.value)?.[fieldFor(row, col)]
}

/** "Left" counts down from the agreed budget (else the first version on screen). */
const referenceVersion = computed(() => {
  const ref = props.ws.summary?.reference?.name
  return props.ws.columns.some((c) => c.version === ref) ? ref : props.ws.columns[0]?.version
})

const sellingOf = (row) => valuesIn(row, latestVersion.value)?.selling_amount || null
const costOf = (row, version) => valuesIn(row, version)?.cost_amount ?? null

function profitOf(row) {
  const selling = sellingOf(row)
  const cost = costOf(row, latestVersion.value)
  return selling == null || cost == null ? null : selling - cost
}

function deltaOf(row) {
  const columns = props.ws.columns
  const first = costOf(row, columns[0].version)
  const last = costOf(row, columns[columns.length - 1].version)
  return first == null || last == null ? null : last - first
}

/** 'new' / 'changed' marker: how this row differs from the version shown before the focus version. */
function changeFlag(row) {
  const columns = props.ws.columns
  const at = columns.findIndex((column) => column.version === focusName.value)
  if (at < 1) return null
  const before = valuesIn(row, columns[at - 1].version)
  const now = valuesIn(row, focusName.value)
  if (now && !before) return 'new'
  if (now && before && Math.abs((now.cost_amount || 0) - (before.cost_amount || 0)) > 0.005) return 'changed'
  return null
}

function display(row, col) {
  const fmt = props.fmt
  if (!applies(row, col)) return ''
  if (col.field || col.itemField) {
    const values = valuesIn(row, focusName.value)
    if (!values) return '—'
    const field = fieldFor(row, col)
    const value = col.itemField ? values.item?.[col.itemField] : values[field]
    if (field === 'adj_percent') return `${value || 0}%`
    if (col.key === 'days' || col.key === 'pages') return value ? fmt.number(value) : '1'
    if (col.number || typeof value === 'number') return value ? fmt.number(value) : ''
    return value ?? ''
  }
  if (col.key === 'left') {
    const agreed = costOf(row, referenceVersion.value)
    const used = (props.ws.actuals.rows[row.row_key]?.Actual || 0) + (props.ws.actuals.rows[row.row_key]?.Committed || 0)
    return agreed == null ? '' : fmt.number(agreed - used)
  }
  if (col.key.startsWith('cost:')) return costOf(row, col.version) == null ? '—' : fmt.number(costOf(row, col.version))
  if (col.key === 'delta') return deltaOf(row) == null ? '' : fmt.signed(deltaOf(row))
  if (col.key === 'actual') return fmt.number(props.ws.actuals.rows[row.row_key]?.Actual) || ''
  if (col.key === 'committed') return fmt.number(props.ws.actuals.rows[row.row_key]?.Committed) || ''
  if (col.key === 'selling') return fmt.number(sellingOf(row)) || ''
  if (col.key === 'profit') return profitOf(row) == null ? '' : fmt.number(profitOf(row))
  if (col.key === 'margin') {
    const selling = sellingOf(row)
    return selling && profitOf(row) != null ? fmt.percent((profitOf(row) / selling) * 100) : ''
  }
  return ''
}

function totalFor(col) {
  const fmt = props.fmt
  const latest = props.ws.versions.find((v) => v.name === latestVersion.value)
  if (col.key === 'description') return 'Total'
  if (col.key === 'selling') return fmt.number(latest?.total_selling)
  if (col.key.startsWith('cost:')) return fmt.number(props.ws.versions.find((v) => v.name === col.version)?.total_cost)
  if (col.key === 'delta') {
    const totals = props.ws.columns.map((c) => props.ws.versions.find((v) => v.name === c.version)?.total_cost)
    return fmt.signed(totals[totals.length - 1] - totals[0])
  }
  if (col.key === 'left') {
    const agreed = props.ws.versions.find((v) => v.name === referenceVersion.value)?.total_cost
    return agreed == null ? '' : fmt.number(agreed - recorded.value.Actual - recorded.value.Committed)
  }
  if (col.key === 'actual') return fmt.number(recorded.value.Actual) || ''
  if (col.key === 'committed') return fmt.number(recorded.value.Committed) || ''
  if (col.key === 'profit') return fmt.number(latest?.total_profit)
  if (col.key === 'margin') return fmt.percent(latest?.margin_pct)
  return ''
}

/** Profit and margin in the total row take the same red / green as the item rows. */
function totalTone(col) {
  const latest = props.ws.versions.find((v) => v.name === latestVersion.value)
  const value = col.key === 'profit' ? latest?.total_profit : col.key === 'margin' ? latest?.margin_pct : null
  if (value == null) return ''
  return value < 0 ? '!text-ink-red-6' : value > 0 ? '!text-ink-green-8' : ''
}

/* ----------------------------------------------------------------- classes */
function isEditable(row, col) {
  if (!canEdit.value || col.type === 'readonly') return false
  if (!valuesIn(row, focusName.value) || !applies(row, col)) return false
  if (row.row_type === 'Category' && ['uom', 'unit_cost'].includes(col.key)) return false
  if (isClientLine(row) && CLIENT_COLS.includes(col.key) && !clientEditable(row)) return false
  if (col.itemField) return false // Quotation item columns are changed in the Quotation
  if (row.row_type !== 'Category' && ['rate', 'pages'].includes(col.key)) return false
  if (row.row_type === 'Adjustment' && ['qty', 'uom', 'days'].includes(col.key)) return false
  if (col.key === 'unit_cost' && (isQuoteLine(row) || isLtaLine(row))) return false
  if (col.key === 'supplier' && isQuoteLine(row)) return false
  return true
}

function cellClasses(row, col, colIndex) {
  const isActive = active.value.key === row.row_key && active.value.col === col.key
  const profit = col.key === 'profit' || col.key === 'margin' ? profitOf(row) : null
  const editable = isEditable(row, col)
  return [
    ALIGN[col.align],
    col.number ? 'is-number' : '',
    isActive && !editable ? 'is-active' : '', // locked or calculated: a grey tint only
    isActive && editable ? 'is-outlined' : '', // editable: an outline says "type here"
    isEditing(row, col) ? 'is-editing !bg-surface-base' : '',
    colIndex === 0 ? 'sheet-frozen' : '',
    colIndex === 0 && active.value.key === row.row_key ? 'is-row-active' : '',
    row.row_type === 'Category' ? 'bg-surface-gray-1' : 'bg-surface-base', // client lines are titles like the total; breakdown rows stay white
    row.row_type === 'Category' ? 'font-semibold text-ink-gray-9' : '',
    row.row_type === 'Adjustment' ? 'italic text-ink-gray-6' : '',
    col.key.startsWith('cost:') && col.version !== focusName.value ? 'text-ink-gray-6' : '',
    !editable && ['qty', 'days', 'pages', 'rate', 'uom', 'unit_cost'].includes(col.key) ? 'text-ink-gray-6' : '',
    valuesIn(row, focusName.value)?.off_quotation ? 'opacity-60' : '',
    profit != null && profit < 0 ? '!text-ink-red-6' : '',
    profit != null && profit > 0 ? 'text-ink-green-6' : '',
    col.key === 'delta' && deltaOf(row) > 0 ? '!text-ink-red-6' : '',
    col.key === 'delta' && deltaOf(row) < 0 ? 'text-ink-green-6' : '',
    col.key === 'actions' ? 'group' : '',
    dropTarget.value?.key === row.row_key ? 'drop-' + dropTarget.value.pos : '',
    dragKey.value && (dragKey.value === row.row_key || dragAncestors.value.has(row.row_key)) ? 'is-dragging' : '',
  ]
}

/* ------------------------------------------------------------ drag & drop */
/* Drag a row by its grip; it only reorders among its own siblings:
   - a cost line moves within its category,
   - a category moves among the categories at its level and takes all its lines with it.
   Hovering any row of another category's block targets that category (before it in its top half, else after). */
const dragKey = ref(null)
const dropTarget = ref(null) // { key, pos: 'before' | 'after' } on a sibling of the dragged row

/** Rows that move with the dragged one (its subtree): they cannot be drop targets. */
const dragAncestors = computed(() => {
  const found = new Set()
  if (!dragKey.value) return found
  const walk = (key) => (index.value.children.get(key) || []).forEach((child) => found.add(child) && walk(child))
  walk(dragKey.value)
  return found
})

/** The sibling of the dragged row that `row` belongs to (itself or an ancestor), or null if outside. */
function siblingFor(row) {
  const parent = index.value.byKey.get(dragKey.value)?.parent_key || ''
  let current = row
  while (current) {
    if ((current.parent_key || '') === parent) return current
    current = index.value.byKey.get(current.parent_key)
  }
  return null
}

function onDragStart(row, event) {
  if (editing.value) cancelEdit()
  dragKey.value = row.row_key
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', row.description || row.row_key)
}

function onDragEnd() {
  dragKey.value = null
  dropTarget.value = null
}

function onDragOver(row, event) {
  if (!dragKey.value || row.row_key === dragKey.value || dragAncestors.value.has(row.row_key)) return
  const sibling = siblingFor(row)
  if (!sibling || sibling.row_key === dragKey.value) return // outside its category: no drop here
  event.preventDefault()
  event.dataTransfer.dropEffect = 'move'
  let pos = 'after'
  if (sibling === row) {
    const rect = event.currentTarget.getBoundingClientRect()
    pos = event.clientY - rect.top < rect.height / 2 ? 'before' : 'after'
  }
  if (dropTarget.value?.key !== sibling.row_key || dropTarget.value.pos !== pos) dropTarget.value = { key: sibling.row_key, pos }
}

function onDrop(row, event) {
  event.preventDefault()
  const target = dropTarget.value
  const moving = dragKey.value
  onDragEnd()
  if (!target || !moving) return
  const parent_key = index.value.byKey.get(moving)?.parent_key || ''
  const siblings = (index.value.children.get(parent_key) || []).filter((key) => key !== moving)
  const before_key = target.pos === 'before' ? target.key : siblings[siblings.indexOf(target.key) + 1] || null
  props.send(focusName.value, [{ op: 'move', row_key: moving, parent_key, before_key }])
}

/* ----------------------------------------------------------------- editing */
/** Descriptions search the Item master (picking one links the item) or keep what you typed as plain text.
 *  Categories list items first (they become quotation lines); cost lines put your text first. */
const typeOf = (row, col) => (col.key === 'description' && row.row_type !== 'Adjustment' ? 'link' : col.type)
const doctypeOf = (row, col) => (col.key === 'description' ? 'Item' : col.doctype)

const isEditing = (row, col) => editing.value && active.value.key === row.row_key && active.value.col === col.key

function select(key, colKey) {
  active.value = { key, col: colKey }
  nextTick(scrollActiveIntoView)
}

function scrollActiveIntoView() {
  const cell = gridEl.value?.querySelector(`[data-cell="${CSS.escape(active.value.key + ':' + active.value.col)}"]`)
  cell?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
}

/** First click selects a cell; a second click on the selected cell opens its editor. A click while another
 *  cell is open saves that one first and only selects the new cell. */
function onCellMouseDown(row, col, event) {
  if (isEditing(row, col)) return
  const selected = active.value.key === row.row_key && active.value.col === col.key
  if (selected && !editing.value && isEditable(row, col)) {
    // The editor focuses itself; without this the browser then moves focus to the grid, the editor
    // blurs and closes again (the "opens and disappears" flicker).
    event?.preventDefault()
    beginEdit(row, col, undefined, true)
    return
  }
  if (!isEditable(row, col)) gridEl.value?.focus()
  if (editing.value) document.activeElement?.blur() // save the cell being edited before moving on
  const go = () => select(row.row_key, col.key)
  if (editing.value) setTimeout(go, 0) // the open editor's blur saves it first
  else go()
}

async function beginEdit(row, col, initial, fromMouse = false) {
  if (!isEditable(row, col)) return
  select(row.row_key, col.key)
  const current = rawValue(row, col)
  draft.value = initial ?? (current == null || current === 0 ? '' : String(current))
  typedStart.value = initial != null || (fromMouse && typeOf(row, col) === 'link')
  typedKey.value = initial != null
  editing.value = true
  if (typeOf(row, col) !== 'link') {
    await nextTick()
    const input = Array.isArray(editor.value) ? editor.value[0] : editor.value
    input?.focus()
    // Typing replaces the old value; a click or Enter selects it so it can be overtyped or kept.
    if (initial != null || (fromMouse && col.type !== 'number')) input?.setSelectionRange(draft.value.length, draft.value.length)
    else input?.select()
  }
}

/** After Tab or Enter in an editor, open the next editable cell so data entry flows without the mouse. */
function editNext(move) {
  moveActive(move)
  const sideways = move === 'left' || move === 'right'
  for (let step = 0; sideways && step < cols.value.length; step += 1) {
    const row = activeRow.value
    const col = cols.value.find((c) => c.key === active.value.col)
    if (row && col && isEditable(row, col)) break
    const before = active.value.key + active.value.col
    moveActive(move)
    if (before === active.value.key + active.value.col) break
  }
  nextTick(() => {
    const row = activeRow.value
    const col = cols.value.find((c) => c.key === active.value.col)
    if (row && col && isEditable(row, col)) beginEdit(row, col)
  })
}

function cancelEdit() {
  editing.value = false
  gridEl.value?.focus()
}

function finishEdit() {
  editing.value = false
  gridEl.value?.focus()
}

function onEditBlur(row, col) {
  if (editing.value) commitText(row, col, draft.value, null)
}

function onEditKey(event, row, col) {
  event.stopPropagation()
  if (event.key === 'Escape') {
    event.preventDefault()
    cancelEdit()
  } else if (event.key === 'Enter') {
    event.preventDefault()
    commitText(row, col, draft.value, event.shiftKey ? 'up' : 'down')
  } else if (event.key === 'Tab') {
    event.preventDefault()
    commitText(row, col, draft.value, event.shiftKey ? 'left' : 'right')
  }
}

async function commitLink(row, col, value, isText = false) {
  if (!editing.value) return
  if (col.key !== 'description') return commitText(row, col, value, 'right')
  finishEdit()
  if (!value) return
  // Typed text renames the row; a free-text cost line has no item (RFQs and POs use the Default Service Item).
  const values = isText ? { description: value, ...(row.row_type === 'Category' ? {} : { item_code: null }) } : { item_code: value }
  if (!isText) values.description = (await api.getItemName(value)) || value
  const source = index.value.byKey.get(row.row_key) || row
  source.description = values.description
  const own = valuesIn(source, focusName.value)
  if (own && 'item_code' in values) own.item_code = values.item_code
  props.send(focusName.value, [{ op: 'update', row_key: row.row_key, values }])
  moveActive('down')
}

function commitText(row, col, text, move) {
  if (!editing.value) return
  const field = col.key === 'description' ? 'description' : fieldFor(row, col)
  let value = text
  if (col.type === 'number') {
    value = text.trim() === '' ? 0 : parseNumber(text)
    if (value == null) {
      toast.error(`"${text}" is not a number`)
      return cancelEdit()
    }
  }
  finishEdit()
  if (col.itemField) {
    const own = valuesIn(row, focusName.value)
    if ((own?.item?.[col.itemField] ?? '') !== text) {
      if (own) own.item = { ...(own.item || {}), [col.itemField]: text }
      props.setItemField(focusName.value, row.row_key, col.itemField, text)
    }
    if (move) editNext(move)
    return
  }
  const previous = col.key === 'description' ? row.description : valuesIn(row, focusName.value)?.[field]
  if ((previous ?? '') !== value && !(previous == null && value === 0)) {
    applyLocally(row, col, field, value)
    props.send(focusName.value, [{ op: 'update', row_key: row.row_key, values: { [field]: value } }])
  }
  if (move) editNext(move)
}

function applyLocally(row, col, field, value) {
  const source = index.value.byKey.get(row.row_key) || row
  if (col.key === 'description') source.description = value
  const values = valuesIn(source, focusName.value)
  if (values) values[field] = value
}

/* -------------------------------------------------------------- navigation */
const NAV_COLS = computed(() => cols.value.filter((col) => col.key !== 'actions'))

function moveActive(direction) {
  const list = rows.value
  const keys = NAV_COLS.value
  const at = list.findIndex((r) => r.row_key === active.value.key)
  const colAt = keys.findIndex((c) => c.key === active.value.col)
  if (direction === 'down' && at < list.length - 1) select(list[at + 1].row_key, active.value.col)
  else if (direction === 'up' && at > 0) select(list[at - 1].row_key, active.value.col)
  else if (direction === 'right') {
    if (colAt < keys.length - 1) select(active.value.key, keys[colAt + 1].key)
    else if (at < list.length - 1) select(list[at + 1].row_key, keys[0].key)
  } else if (direction === 'left') {
    if (colAt > 0) select(active.value.key, keys[colAt - 1].key)
    else if (at > 0) select(list[at - 1].row_key, keys[keys.length - 1].key)
  }
}

function onGridKey(event) {
  if (editing.value) return
  const row = rows.value.find((r) => r.row_key === active.value.key) || null
  const col = cols.value.find((c) => c.key === active.value.col)
  if (!row) {
    if (rows.value.length && ['ArrowDown', 'ArrowUp', 'Enter'].includes(event.key)) {
      event.preventDefault()
      select(rows.value[0].row_key, 'description')
    }
    return
  }
  const mod = event.ctrlKey || event.metaKey
  if (event.altKey && handleRowShortcut(event)) return
  if (mod && event.key === 'Enter') return stop(event, () => addLine())
  if (mod && event.key.toLowerCase() === 'd') return stop(event, () => duplicate())
  if (mod && event.key === 'Delete') return stop(event, () => remove())
  if (event.shiftKey && event.key === 'Enter') return stop(event, () => emit('details', row))
  switch (event.key) {
    case 'ArrowDown': return stop(event, () => moveActive('down'))
    case 'ArrowUp': return stop(event, () => moveActive('up'))
    case 'ArrowRight':
      if (col.key === 'description' && row.hasChildren && collapsed.value.has(row.row_key)) return stop(event, () => toggle(row.row_key))
      return stop(event, () => moveActive('right'))
    case 'ArrowLeft':
      if (col.key === 'description' && row.hasChildren && !collapsed.value.has(row.row_key)) return stop(event, () => toggle(row.row_key))
      return stop(event, () => moveActive('left'))
    case 'Tab': return stop(event, () => moveActive(event.shiftKey ? 'left' : 'right'))
    case 'Enter':
    case 'F2': return stop(event, () => beginEdit(row, col))
    case 'Delete':
    case 'Backspace':
      return stop(event, () => clearCell(row, col))
    default:
      if (event.key.length === 1 && !mod && !event.altKey) {
        event.preventDefault()
        beginEdit(row, col, typeOf(row, col) === 'link' ? event.key : event.key)
      }
  }
}

function stop(event, action) {
  event.preventDefault()
  action()
}

function handleRowShortcut(event) {
  const actions = { ArrowUp: () => moveRow(-1), ArrowDown: () => moveRow(1) } // reorder among siblings only
  const action = actions[event.key]
  if (!action) return false
  event.preventDefault()
  action()
  return true
}

function clearCell(row, col) {
  if (!isEditable(row, col) || col.key === 'description') return
  editing.value = true
  commitText(row, col, '', null)
}

/* ------------------------------------------------------------ row actions */
function requireRow() {
  if (!canEdit.value) return toast.error('This version is read-only. Pick a Working version to edit.')
  return activeRow.value || null
}

async function addRow(values, { asChild, topLevel } = {}) {
  if (!canEdit.value) return toast.error('This version is read-only. Pick a Working version to edit.')
  const row = activeRow.value
  const temp = 'tmp' + Date.now()
  let parent_key = ''
  let before_key = null
  if (row && topLevel) {
    // A new category is a new quotation line: top level, right after the block you are in.
    let top = row
    while (top.parent_key && index.value.byKey.has(top.parent_key)) top = index.value.byKey.get(top.parent_key)
    const roots = index.value.children.get('') || []
    before_key = roots[roots.indexOf(top.row_key) + 1] || null
  } else if (row) {
    const childMode = asChild ?? row.row_type === 'Category'
    parent_key = childMode ? row.row_key : row.parent_key || ''
    if (!childMode) {
      const siblings = index.value.children.get(parent_key) || []
      before_key = siblings[siblings.indexOf(row.row_key) + 1] || null
    }
  } else if (values.row_type !== 'Category') {
    // nothing selected: a line goes into the last category (lines always live inside one)
    const categories = (index.value.children.get('') || []).filter((key) => index.value.byKey.get(key)?.row_type === 'Category')
    if (!categories.length) return toast.error('Add a category first: lines go inside a category.')
    parent_key = categories[categories.length - 1]
  }
  if (parent_key) collapsed.value.delete(parent_key)
  const created = await props.send(focusName.value, [{ op: 'add', temp_id: temp, parent_key, before_key, values }])
  const key = created[temp]
  if (!key) return
  await nextTick()
  select(key, 'description')
  const added = props.ws.rows.find((r) => r.row_key === key)
  if (added) beginEdit({ ...added, hasChildren: false }, cols.value[0])
}

const addLine = () => addRow({ row_type: 'Cost Item' })
const addCategory = () => {
  if (props.focus?.syncs_quotation) return toast.error('Client lines come from the Quotation: add them there, then Sync')
  addRow({ row_type: 'Category' }, { topLevel: true })
}

const sendFor = (op) => props.send(focusName.value, [op])

function moveRow(direction) {
  const row = requireRow()
  const op = row && moveOp(row, index.value.children, direction)
  if (op) sendFor(op)
}

function duplicate() {
  const row = requireRow()
  if (row) sendFor({ op: 'duplicate', row_key: row.row_key })
}

function remove() {
  const row = requireRow()
  if (!row) return
  if (row.hasChildren && !window.confirm(`Delete "${row.description}" and everything under it?`)) return
  moveActive('down')
  if (active.value.key === row.row_key) moveActive('up')
  sendFor({ op: 'delete', row_key: row.row_key })
}

/** A draft Variation Sales Order for a line added after agreement; it goes through the normal approval. */
async function billToClient(row) {
  const rate = valuesIn(row, focusName.value)?.rate
  if (!rate) return toast.error(`Set a Rate on "${row.description}" first: that is what the client is billed`)
  if (!window.confirm(`Draft a Variation Sales Order for "${row.description}"?`)) return
  const result = await revisionAction('billToClient', focusName.value, [row.row_key])
  if (result) {
    toast.success(`${result.sales_order} drafted. Send it for approval like any Sales Order.`)
    openPanel('Sales Order', result.sales_order)
  }
}

/** Run a row action against a specific row (from its hover menu). */
function act(row, action) {
  select(row.row_key, 'description')
  action()
}

function rowMenu(row) {
  const isCategory = row.row_type === 'Category'
  const items = [
    { label: 'Line details…', onClick: () => act(row, () => emit('details', row)) },
    { label: isCategory ? 'Add line inside' : 'Add line below', onClick: () => act(row, addLine) },
  ]
  if (isCategory && !row.parent_key && anyValue(row, 'after_agreement') && !anyValue(row, 'variation_order') && props.ws.plan.can_write) {
    items.push({ label: 'Bill to client…', onClick: () => billToClient(row) })
  }
  items.push(
    { label: 'Move up', onClick: () => act(row, () => moveRow(-1)) },
    { label: 'Move down', onClick: () => act(row, () => moveRow(1)) },
    { label: 'Duplicate', onClick: () => act(row, duplicate) },
    { label: 'Delete', theme: 'red', onClick: () => act(row, remove) },
  )
  return items
}

watch(
  () => props.focus?.name,
  () => {
    editing.value = false
  },
)

defineExpose({
  columns: { available, chosen, setChoice, applyView, views: VIEWS, fixed: FIXED_COLUMNS },
  activeRow,
  addLine,
  addCategory,
  focus: () => gridEl.value?.focus(),
})
</script>
