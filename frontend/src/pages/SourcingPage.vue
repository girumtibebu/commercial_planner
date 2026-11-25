<template>
  <PageFrame subtitle="Lines priced by Quote (RFQ): send RFQs, compare bids side by side, pick the winners, then order.">
    <template #actions>
      <Button v-if="!selected.size" :disabled="!needingQuotes.length || busy" @click="selected = new Set(needingQuotes.map((row) => row.row_key))">
        <template #prefix><span class="lucide-list-checks size-3.5" /></template>
        Select lines to quote ({{ needingQuotes.length }})
      </Button>
      <Button v-else variant="solid" :disabled="busy" @click="rfqOpen = true">
        <template #prefix><span class="lucide-send size-3.5" /></template>
        Send RFQ ({{ selected.size }})
      </Button>
      <Button :disabled="!src?.editable || !toPick.length || busy" @click="act(() => api.pullQuotes(version), (r) => `Picked the lowest bid on ${r.updated.length} line(s)`)">
        <template #prefix><span class="lucide-arrow-down-wide-narrow size-3.5" /></template>
        Use lowest bids
      </Button>
      <Button :disabled="!canOrder || busy" @click="act(() => api.createPurchaseOrders(version, false), poToast)">Create missing POs</Button>
      <Button :disabled="!canSettle || busy" @click="act(() => api.settleInternal(version), settleToast)">Settle division work</Button>
    </template>

    <div v-if="src && !src.settings.ready" class="rounded-lg border border-outline-amber-2 bg-surface-amber-1 px-4 py-2 text-sm text-ink-amber-8">
      Set the lead cost center, internal accounts and divisions in
      <button class="underline" @click="openSettings">Settings</button>
      before raising orders or settling.
    </div>
    <div v-if="loadError" class="rounded-lg border border-outline-red-3 bg-surface-red-2 p-3 text-sm text-ink-red-8">{{ loadError }}</div>

    <!-- where purchasing stands -->
    <div v-if="src" class="grid gap-2">
      <span class="cp-section-title">Purchasing</span>
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <div v-for="step in steps" :key="step.label" class="cp-stat">
          <span class="cp-stat-label">{{ step.label }}</span>
          <span class="cp-stat-value" :class="step.count ? step.tone : '!text-ink-gray-4'">{{ step.count }}</span>
          <span class="cp-stat-sub">{{ step.count ? step.note : step.empty }}</span>
        </div>
      </div>
    </div>

    <!-- bid board -->
    <span v-if="src" class="cp-section-title -mb-1">Bids</span>
    <div v-if="src" class="overflow-x-auto rounded-xl border border-outline-gray-2 bg-surface-base">
      <table class="w-full min-w-[960px] border-collapse text-sm tabular-nums">
        <thead>
          <tr class="border-b border-outline-gray-2 bg-surface-gray-1 text-sm text-ink-gray-6">
            <th class="w-9 px-3 py-2 text-center"><input type="checkbox" :checked="allSelected" :disabled="!lines.length" @change="toggleAll" /></th>
            <th class="min-w-[220px] px-3 py-2 text-left font-normal">Line</th>
            <th class="px-3 py-2 text-center font-normal">Qty</th>
            <th class="px-3 py-2 text-right font-normal">Unit cost</th>
            <th v-for="b in src.bidders" :key="b.supplier" class="min-w-[150px] border-l border-outline-gray-1 px-3 py-2 text-center align-top font-normal normal-case tracking-normal">
              <div class="flex items-center justify-center gap-1.5 text-[12px] text-ink-gray-9">
                <span class="truncate">{{ b.supplier }}</span>
              </div>
              <div class="mt-1 flex flex-wrap items-center justify-center gap-1">
                <span class="cp-chip" :class="b.internal ? 'bg-surface-blue-2 text-ink-blue-8' : 'bg-surface-gray-2 text-ink-gray-7'">{{ b.internal ? 'Division' : 'External' }}</span>
                <span class="cp-chip" :class="vendorStatus(b).tone">{{ vendorStatus(b).label }}</span>
              </div>
              <div v-if="b.total != null" class="mt-1 text-[11px] text-ink-gray-5">bid total {{ fmt.number(b.total) }}</div>
            </th>
            <th class="px-3 py-2 text-center font-normal">Status</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in shown"
            :key="row.row_key"
            :data-line="row.row_key"
            class="border-b border-outline-gray-1 last:border-0"
            :class="[
              row.row_type === 'Category' ? 'bg-surface-gray-1 font-semibold text-ink-gray-9' : 'hover:bg-surface-gray-1',
              row.row_key === focusLine ? '!bg-surface-amber-1' : '',
            ]"
          >
            <td class="px-3 py-2 text-center">
              <input v-if="row.row_type === 'Cost Item'" type="checkbox" :checked="selected.has(row.row_key)" @change="toggle(row.row_key)" />
            </td>
            <td class="px-3 py-2 text-left" :style="{ paddingLeft: 12 + row.depth * 18 + 'px' }">
              <div class="truncate">{{ row.description }}</div>
            </td>
            <td class="px-3 py-2 text-center">{{ row.qty }}</td>
            <td class="px-3 py-2 text-right">{{ row.row_type === 'Cost Item' ? fmt.number(row.unit_cost) : fmt.number(row.cost_amount) }}</td>
            <td v-for="b in src.bidders" :key="b.supplier" class="border-l border-outline-gray-1 px-2 py-1.5 text-center">
              <template v-if="row.row_type === 'Cost Item'">
                <button
                  v-if="bid(row, b)"
                  class="w-full rounded-md px-2 py-1 text-right transition-colors"
                  :class="bidClass(row, b)"
                  :disabled="!src.editable || busy || isPicked(row, b)"
                  :title="isPicked(row, b) ? 'Picked' : src.editable ? 'Use this bid' : ''"
                  @click="pick(row, b)"
                >
                  <div class="flex items-center justify-end gap-1.5">
                    <span v-if="isLowest(row, b)" class="text-[10px] font-medium uppercase text-ink-green-6">lowest</span>
                    <span class="font-medium">{{ fmt.number(bid(row, b).rate) }}</span>
                    <!-- radio: the offer you choose prices the line here and in the cost plan -->
                    <span
                      class="ml-0.5 size-3.5 shrink-0"
                      :class="isPicked(row, b) ? 'lucide-circle-dot text-ink-green-6' : 'lucide-circle text-ink-gray-4'"
                    />
                  </div>
                  <div class="text-[11px] text-ink-gray-5">× {{ row.qty }} = {{ fmt.number(bid(row, b).rate * row.qty) }}</div>
                  <div v-if="isPicked(row, b) && row.purchase_order" class="text-[11px] font-medium text-ink-green-7">ordered · PO {{ shortName(row.purchase_order) }}</div>
                </button>
                <span v-else-if="invited(row, b)" class="text-xs text-ink-gray-4">awaiting</span>
              </template>
              <span v-else-if="categoryBid(row, b) != null" class="text-xs font-medium text-ink-gray-7">{{ fmt.number(categoryBid(row, b)) }}</span>
            </td>
            <td class="px-3 py-2 text-center">
              <span v-if="statusOf(row)" class="cp-chip" :class="statusOf(row).tone">{{ statusOf(row).label }}</span>
            </td>
          </tr>
          <tr v-if="!shown.length">
            <td :colspan="5 + src.bidders.length" class="px-3 py-8 text-center text-ink-gray-5">
              No lines to quote. In the cost plan, set a line's <b>Cost from</b> to <b>Quote (RFQ)</b> and it appears here.
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!src.bidders.length && shown.length" class="border-t border-outline-gray-1 px-4 py-3 text-sm text-ink-gray-5">
        No bids yet. Tick the lines to quote (or <b>Select lines to quote</b>) and <b>Send RFQ</b>: each invited supplier gets a column here.
      </div>
    </div>

    <!-- vendors: each one's documents, side by side -->
    <span v-if="src?.bidders.length" class="cp-section-title -mb-1">Vendors</span>
    <div v-if="src?.bidders.length" class="overflow-x-auto rounded-xl border border-outline-gray-2 bg-surface-base">
      <table class="w-full min-w-[960px] border-collapse text-sm tabular-nums">
        <thead>
          <tr class="border-b border-outline-gray-2 bg-surface-gray-1 text-left text-ink-gray-6">
            <th class="px-3 py-2 font-normal">Vendor</th>
            <th class="px-3 py-2 font-normal">Status</th>
            <th class="px-3 py-2 font-normal">RFQ → Bid (Supplier Quotation)</th>
            <th class="px-3 py-2 text-center font-normal">Won</th>
            <th class="px-3 py-2 font-normal">Purchase Order</th>
            <th class="px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          <tr v-for="b in src.bidders" :key="b.supplier" class="border-b border-outline-gray-1 align-top last:border-0">
            <td class="px-3 py-2">
              <div class="font-medium text-ink-gray-9">{{ b.supplier }}</div>
              <span class="cp-chip mt-1" :class="b.internal ? 'bg-surface-blue-2 text-ink-blue-8' : 'bg-surface-gray-2 text-ink-gray-7'">{{ b.internal ? 'Division' : 'External' }}</span>
            </td>
            <td class="px-3 py-2"><span class="cp-chip" :class="vendorStatus(b).tone">{{ vendorStatus(b).label }}</span></td>
            <td class="px-3 py-2">
              <!-- one block per RFQ: the vendor's current bid on it, and the bids it replaced -->
              <div v-for="rfq in b.rfq_docs" :key="rfq.name" class="border-b border-dashed border-outline-gray-2 py-1.5 first:pt-0 last:border-0 last:pb-0">
                <div class="flex flex-wrap items-center gap-2">
                  <DocLink doctype="Request for Quotation" :name="rfq.name" label="RFQ" />
                  <span class="text-xs text-ink-gray-5">sent {{ fmt.date(rfq.transaction_date) }}<template v-if="rfq.docstatus === 0"> · draft</template></span>
                  <span class="lucide-arrow-right size-3 text-ink-gray-4" />
                  <template v-if="rfq.bids.length">
                    <DocLink doctype="Supplier Quotation" :name="rfq.bids[0].name" label="Bid" />
                    <span class="text-xs text-ink-gray-5">
                      {{ rfq.bids[0].docstatus === 0 ? 'draft' : 'submitted' }} · {{ fmt.number(rfq.bids[0].total) }}<template v-if="rfq.bids[0].valid_till"> · valid to {{ fmt.date(rfq.bids[0].valid_till) }}</template>
                    </span>
                    <Popover v-if="rfq.bids[0].attachments.length">
                      <template #target="{ togglePopover }">
                        <button class="cp-chip bg-surface-gray-2 text-ink-gray-8 hover:bg-surface-gray-3" :title="`${rfq.bids[0].attachments.length} document(s)`" @click="togglePopover">
                          <span class="lucide-paperclip size-3" /> {{ rfq.bids[0].attachments.length }}
                        </button>
                      </template>
                      <template #body>
                        <div class="mt-1 min-w-56 rounded-lg border border-outline-gray-2 bg-surface-base p-1 text-left shadow-xl">
                          <a v-for="f in rfq.bids[0].attachments" :key="f.file_url" :href="f.file_url" target="_blank" class="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-ink-gray-8 hover:bg-surface-gray-2">
                            <span class="lucide-file-text size-3.5 text-ink-gray-5" /> <span class="truncate">{{ f.file_name }}</span>
                          </a>
                        </div>
                      </template>
                    </Popover>
                    <Button size="sm" variant="ghost" :disabled="busy" title="Record a new bid from this vendor on this RFQ" @click="openBid(b, rfq, rfq.bids[0])">Revise</Button>
                  </template>
                  <template v-else>
                    <span class="text-xs text-ink-gray-4">no bid</span>
                    <Button size="sm" :disabled="rfq.docstatus !== 1 || busy" title="Type in the vendor's prices" @click="openBid(b, rfq)">
                      <template #prefix><span class="lucide-plus size-3.5" /></template>
                      Enter bid
                    </Button>
                  </template>
                </div>
                <div v-if="rfq.bids.length > 1" class="mt-1">
                  <button class="text-xs text-ink-gray-5 hover:text-ink-gray-8" @click="toggleEarlier(b.supplier + rfq.name)">
                    {{ earlierOpen.has(b.supplier + rfq.name) ? 'Hide earlier bids' : `+${rfq.bids.length - 1} earlier bid${rfq.bids.length > 2 ? 's' : ''}` }}
                  </button>
                  <template v-if="earlierOpen.has(b.supplier + rfq.name)">
                    <div v-for="old in rfq.bids.slice(1)" :key="old.name" class="flex items-center gap-2 py-0.5 pl-3 opacity-70">
                      <DocLink doctype="Supplier Quotation" :name="old.name" label="Bid" />
                      <span class="text-xs text-ink-gray-5">revised · {{ fmt.number(old.total) }} · {{ fmt.date(old.transaction_date) }}</span>
                    </div>
                  </template>
                </div>
              </div>
            </td>
            <td class="px-3 py-2 text-center">
              <span v-if="wonLines(b).length">{{ wonLines(b).length }} of {{ invitedLines(b).length }}</span>
              <span v-else class="text-ink-gray-4">—</span>
            </td>
            <td class="px-3 py-2">
              <div v-for="po in vendorOrders(b)" :key="po.name" class="flex items-center gap-2 py-0.5">
                <DocLink doctype="Purchase Order" :name="po.name" label="PO" />
                <span class="text-xs text-ink-gray-5">{{ po.docstatus === 0 ? 'Draft' : po.status }} · {{ fmt.number(po.grand_total) }}</span>
              </div>
              <span v-if="!vendorOrders(b).length" class="text-ink-gray-4">—</span>
            </td>
            <td class="px-3 py-2 text-right">
              <Button
                v-if="toOrder(b).length"
                size="sm"
                :disabled="!orderable || busy"
                :title="orderable ? `Draft a PO for ${toOrder(b).length} line(s)` : 'POs are raised once the Sales Order is submitted'"
                @click="act(() => api.createPurchaseOrders(version, false, b.supplier), poToast)"
              >Create PO</Button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- planned P&L per cost center -->
    <div v-if="src?.cost_centers?.length" class="grid gap-2">
      <span class="cp-section-title">Planned profit by cost center</span>
      <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div v-for="cc in src.cost_centers" :key="cc.cost_center" class="cp-stat">
          <span class="cp-stat-label">{{ cc.cost_center || 'No lead cost center' }}</span>
          <span class="cp-stat-value" :class="cc.revenue - cc.cost < 0 ? '!text-ink-red-6' : ''">{{ fmt.money(cc.revenue - cc.cost) }}</span>
          <span class="cp-stat-sub">
            {{ cc.kind === 'Lead' ? 'Client price' : 'Internal income' }} {{ fmt.number(cc.revenue) }}<template v-if="cc.cost"> · cost {{ fmt.number(cc.cost) }}</template>
          </span>
        </div>
      </div>
    </div>

    <Dialog v-model="bidOpen" :options="{ title: bidCtx ? `${bidCtx.revise ? 'Revise' : 'Enter'} bid · ${bidCtx.supplier}` : 'Bid', size: '2xl' }">
      <template #body-content>
        <div v-if="bidCtx" class="grid gap-3 text-sm">
          <p class="text-ink-gray-6">
            Prices quoted on RFQ {{ shortName(bidCtx.rfq) }}, in {{ bidCtx.currency }}. Leave a rate empty for an item the vendor did not quote.
          </p>
          <table class="w-full border-collapse tabular-nums">
            <thead>
              <tr class="border-b border-outline-gray-2 text-left text-ink-gray-6">
                <th class="py-1.5 pr-3 font-normal">Item</th>
                <th class="px-3 py-1.5 text-right font-normal">Qty</th>
                <th class="px-3 py-1.5 text-right font-normal">Rate</th>
                <th class="py-1.5 pl-3 text-right font-normal">Amount</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in bidCtx.items" :key="item.rfq_item" class="border-b border-outline-gray-1">
                <td class="py-1.5 pr-3">
                  <div class="text-ink-gray-9">{{ item.description }}</div>
                  <div class="text-xs text-ink-gray-5">{{ item.item_code }}</div>
                </td>
                <td class="px-3 py-1.5 text-right">{{ item.qty }} {{ item.uom }}</td>
                <td class="px-3 py-1.5 text-right">
                  <input v-model.number="item.rate" type="number" min="0" step="any" class="cp-input w-32 text-right" :aria-label="`Rate for ${item.description}`" />
                </td>
                <td class="py-1.5 pl-3 text-right">{{ item.rate > 0 ? fmt.number(item.rate * item.qty) : '—' }}</td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <td colspan="3" class="py-1.5 pr-3 text-right text-ink-gray-6">Bid total</td>
                <td class="py-1.5 pl-3 text-right font-medium text-ink-gray-9">{{ fmt.number(bidTotal) }}</td>
              </tr>
            </tfoot>
          </table>
          <div class="grid gap-3 sm:grid-cols-2">
            <label class="grid gap-1">
              <span class="text-ink-gray-6">Valid till</span>
              <input v-model="bidValid" type="date" class="cp-input" />
            </label>
            <label class="grid gap-1">
              <span class="text-ink-gray-6">Vendor's documents</span>
              <input type="file" multiple class="text-sm" @change="bidFiles = [...$event.target.files]" />
            </label>
          </div>
          <p v-if="bidCtx.revise" class="text-xs text-ink-gray-5">
            Saves a new quotation; {{ shortName(bidCtx.revise) }} stays on record as revised. Lines already priced from it keep that price until you pick the new bid.
          </p>
          <div class="flex justify-end gap-2">
            <Button label="Cancel" @click="bidCtx = null" />
            <Button :disabled="!bidReady || busy" label="Save draft" @click="saveBid(false)" />
            <Button variant="solid" :disabled="!bidReady || busy" label="Save and submit" @click="saveBid(true)" />
          </div>
        </div>
      </template>
    </Dialog>

    <Dialog v-model="rfqOpen" :options="{ title: `Request quotes for ${selected.size} line(s)`, size: 'xl' }">
      <template #body-content>
        <div class="grid gap-3 text-sm">
          <div class="rounded-lg bg-surface-gray-1 px-3 py-2 text-xs text-ink-gray-6">
            {{ selectedLines.map((row) => `${row.description} × ${row.qty}`).join(' · ') }}
          </div>
          <div class="grid gap-1">
            <span class="text-ink-gray-6">Send to</span>
            <SupplierPicker v-if="rfqOpen" v-model="suppliers" :divisions="src?.divisions || []" />
          </div>
          <label class="grid gap-1">
            <span class="text-ink-gray-6">Message to suppliers</span>
            <textarea v-model="message" rows="2" class="cp-input" placeholder="Event date, venue, delivery terms…" />
          </label>
          <p class="text-xs text-ink-gray-5">Suppliers price exactly these items and quantities, on the supplier portal or in Desk, and can attach documents to their quotation.</p>
          <div class="flex justify-end gap-2">
            <Button label="Cancel" @click="rfqOpen = false" />
            <Button variant="solid" :disabled="!suppliers.length || busy" :label="`Create RFQ for ${suppliers.length} supplier(s)`" @click="sendRfq" />
          </div>
        </div>
      </template>
    </Dialog>
  </PageFrame>
</template>

<script setup>
import { computed, h, inject, nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Button, Dialog, Popover, toast } from 'frappe-ui'
import PageFrame from '../components/PageFrame.vue'
import SupplierPicker from '../components/SupplierPicker.vue'
import { api } from '../api'
import { readError } from '../useWorkspace'

const { ws, fmt, focusVersion, load, deskPath, openPanel, openSettings } = inject('cp')

const src = ref(null)
const loadError = ref(null)
const busy = ref(false)
const selected = ref(new Set())
const version = computed(() => focusVersion.value?.name)

async function refresh() {
  if (!version.value) return
  try {
    src.value = await api.getSourcing(version.value)
    loadError.value = null
  } catch (err) {
    loadError.value = readError(err)
  }
}
watch(version, () => {
  selected.value = new Set()
  refresh()
}, { immediate: true })
// Live with the cost plan: any edit there (or the header's quotation actions) reloads the workspace.
watch(ws, () => refresh())

/* ------------------------------------------------------------------ lines */
const costLines = computed(() => (src.value?.rows || []).filter((row) => row.row_type === 'Cost Item'))
/** Only lines priced by Quote (RFQ) are sourced here; Manual and LTA lines are priced in the cost plan. */
const lines = computed(() => costLines.value.filter((row) => row.pricing_basis === 'Requirement'))
const quoteLines = lines
/** The quote lines and the categories above them, in plan order. */
const shown = computed(() => {
  const rows = src.value?.rows || []
  const keep = new Set()
  const byKey = new Map(rows.map((row) => [row.row_key, row]))
  for (const row of lines.value) {
    for (let at = row; at && !keep.has(at.row_key); at = byKey.get(at.parent_key)) keep.add(at.row_key)
  }
  return rows.filter((row) => keep.has(row.row_key))
})
const needingQuotes = computed(() => quoteLines.value.filter((row) => !row.rfq))
const quotesOf = (row) => src.value?.quotes[row.row_key] || []
const toPick = computed(() => lines.value.filter((row) => quotesOf(row).length && !row.supplier_quotation))
const selectedLines = computed(() => lines.value.filter((row) => selected.value.has(row.row_key)))
const allSelected = computed(() => lines.value.length > 0 && lines.value.every((row) => selected.value.has(row.row_key)))

const steps = computed(() => [
  { label: 'To quote', count: needingQuotes.value.length, tone: '!text-ink-amber-8', note: 'Lines with no RFQ yet', empty: 'Every quote line is out' },
  { label: 'Waiting for bids', count: quoteLines.value.filter((r) => r.rfq && !quotesOf(r).length).length, tone: '', note: 'RFQ sent, no bid yet', empty: 'Nothing waiting' },
  { label: 'Bids to pick', count: toPick.value.length, tone: '!text-ink-blue-8', note: 'Compare and pick below', empty: 'Nothing to pick' },
  { label: 'Picked', count: lines.value.filter((r) => r.supplier_quotation).length, tone: '!text-ink-green-8', note: 'Priced from a bid', empty: 'No bid picked yet' },
  { label: 'Ordered', count: lines.value.filter((r) => r.purchase_order).length, tone: '', note: 'On a Purchase Order', empty: 'No orders yet' },
])

function toggle(key) {
  const next = new Set(selected.value)
  next.has(key) ? next.delete(key) : next.add(key)
  selected.value = next
}
function toggleAll() {
  selected.value = allSelected.value ? new Set() : new Set(lines.value.map((row) => row.row_key))
}

/* ------------------------------------------------------------------- bids */
/** The bidder's quote for a line: from one of their current bids if it covers the line, else any of theirs. */
function bid(row, bidder) {
  const mine = quotesOf(row).filter((q) => q.supplier === bidder.supplier)
  return mine.find((q) => bidder.current.includes(q.supplier_quotation)) || mine[0] || null
}
const invited = (row, bidder) => (row.rfqs || []).some((rfq) => bidder.rfqs.includes(rfq))

const isPicked = (row, bidder) => Boolean(row.supplier_quotation) && bid(row, bidder)?.supplier_quotation === row.supplier_quotation
function isLowest(row, bidder) {
  const rates = quotesOf(row).map((q) => q.rate)
  return rates.length > 1 && bid(row, bidder)?.rate === Math.min(...rates)
}
function bidClass(row, bidder) {
  if (isPicked(row, bidder)) return 'bg-surface-green-2 text-ink-gray-9'
  return src.value.editable ? 'text-ink-gray-8 hover:bg-surface-gray-2' : 'text-ink-gray-8'
}

/** A bidder's total over the lines of a category (to compare whole packages). */
function categoryBid(row, bidder) {
  const under = []
  const collect = (key) =>
    src.value.rows.filter((r) => r.parent_key === key).forEach((r) => (r.row_type === 'Category' ? collect(r.row_key) : under.push(r)))
  collect(row.row_key)
  const priced = under.map((r) => bid(r, bidder)).filter(Boolean)
  if (!priced.length) return null
  return under.reduce((sum, r) => sum + (bid(r, bidder) ? bid(r, bidder).rate * r.qty : 0), 0)
}

function pick(row, bidder) {
  const quote = bid(row, bidder)
  act(() => api.selectQuote(version.value, row.row_key, quote.supplier_quotation), (r) => `${r.row}: using ${r.supplier} at ${fmt.value.number(r.rate)}`)
}

function statusOf(row) {
  if (row.row_type !== 'Cost Item') return null
  if (row.purchase_order) return { label: row.settlement ? 'Settled' : 'Ordered', tone: 'bg-surface-gray-2 text-ink-gray-8' }
  if (row.supplier_quotation) return { label: 'Bid picked', tone: 'bg-surface-green-2 text-ink-green-8' }
  if (!row.rfq) return { label: 'To quote', tone: 'bg-surface-amber-2 text-ink-amber-8' }
  const count = quotesOf(row).length
  if (!count) return { label: 'Waiting', tone: 'bg-surface-gray-2 text-ink-gray-7' }
  return { label: `${count} bid${count > 1 ? 's' : ''}: pick`, tone: 'bg-surface-blue-2 text-ink-blue-8' }
}

const shortName = (name) => name.replace(/^.*-(\d+)$/, '#$1')
/** A document chip that opens in the side panel. */
const DocLink = (props) =>
  h('a', {
    class: 'cp-chip bg-surface-gray-2 font-mono text-ink-gray-8 hover:bg-surface-gray-3',
    href: deskPath(props.doctype, props.name),
    title: `${props.doctype} ${props.name}`,
    onClick: (event) => {
      event.preventDefault()
      openPanel(props.doctype, props.name)
    },
  }, `${props.label} ${shortName(props.name)}`)
DocLink.props = ['doctype', 'name', 'label']

const invitedLines = (bidder) => lines.value.filter((row) => (row.rfqs || []).some((rfq) => bidder.rfqs.includes(rfq)))
const wonLines = (bidder) => lines.value.filter((row) => row.supplier_quotation && bidder.all_bids.includes(row.supplier_quotation))
const vendorOrders = (bidder) => Object.values(src.value?.purchase_orders || {}).filter((po) => po.supplier === bidder.supplier)
const toOrder = (bidder) => costLines.value.filter((row) => row.supplier === bidder.supplier && row.unit_cost > 0 && !row.purchase_order)
const orderable = computed(() => src.value?.plan.sales_order_docstatus === 1)

// "?line=<row_key>" (from the cost plan's sourcing chip): highlight that line and bring it into view
const route = useRoute()
const focusLine = computed(() => route.query.line || null)
watch([focusLine, src], async () => {
  if (!focusLine.value || !src.value) return
  await nextTick()
  document.querySelector(`[data-line="${focusLine.value}"]`)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
})

/** Where this vendor stands: no bid yet, bid in, won lines, or ordered. */
function vendorStatus(bidder) {
  const won = wonLines(bidder)
  if (won.some((row) => row.purchase_order)) return { label: 'Ordered', tone: 'bg-surface-gray-3 text-ink-gray-8' }
  if (won.length) return { label: `Won ${won.length} line${won.length > 1 ? 's' : ''}`, tone: 'bg-surface-green-2 text-ink-green-8' }
  if (bidder.current.length) return { label: 'Bid received', tone: 'bg-surface-blue-2 text-ink-blue-8' }
  return { label: 'Awaiting bid', tone: 'bg-surface-amber-2 text-ink-amber-8' }
}

/* --------------------------------------------------------------- actions */
// POs and settlements cover every priced line with a supplier, Manual and LTA lines too
const canOrder = computed(() => src.value?.plan.sales_order_docstatus === 1 && costLines.value.some((row) => row.supplier && row.unit_cost > 0 && !row.purchase_order))
const canSettle = computed(() => src.value?.settings.ready && costLines.value.some((row) => row.internal && row.purchase_order && !row.settlement))

/** Run one sourcing action, show what it did, and refresh both this view and the cost plan. */
async function act(request, describe) {
  busy.value = true
  try {
    const response = await request()
    src.value = response.sourcing
    toast.success(describe(response.result))
    await load()
  } catch (err) {
    toast.error(readError(err))
  } finally {
    busy.value = false
  }
}

const poToast = (r) => `Created ${r.map((po) => po.purchase_order).join(', ')}`
const settleToast = (r) => (r.settled.length ? `Settled ${r.settled.map((s) => s.journal_entry).join(', ')}` : 'Nothing settled') + (r.waiting_submit.length ? `; submit ${r.waiting_submit.join(', ')} first` : '')

// earlier (revised) bids, per vendor and RFQ
const earlierOpen = ref(new Set())
function toggleEarlier(key) {
  const next = new Set(earlierOpen.value)
  next.has(key) ? next.delete(key) : next.add(key)
  earlierOpen.value = next
}

// bid entry: the vendor's prices on one RFQ, typed in here instead of in Desk
const bidCtx = ref(null)
const bidValid = ref('')
const bidFiles = ref([])
const bidOpen = computed({ get: () => Boolean(bidCtx.value), set: (open) => { if (!open) bidCtx.value = null } })
const bidRates = computed(() => Object.fromEntries((bidCtx.value?.items || []).filter((i) => i.rate > 0).map((i) => [i.rfq_item, i.rate])))
const bidReady = computed(() => Object.keys(bidRates.value).length > 0)
const bidTotal = computed(() => (bidCtx.value?.items || []).reduce((sum, i) => sum + (i.rate > 0 ? i.rate * i.qty : 0), 0))

async function openBid(bidder, rfq, current) {
  try {
    const form = await api.bidForm(version.value, rfq.name, bidder.supplier, current?.name)
    bidValid.value = current?.valid_till || ''
    bidFiles.value = []
    bidCtx.value = { supplier: bidder.supplier, rfq: rfq.name, revise: current?.name || null, ...form }
  } catch (err) {
    toast.error(readError(err))
  }
}

function saveBid(submit) {
  const ctx = bidCtx.value
  const rates = bidRates.value
  const files = bidFiles.value
  act(async () => {
    const response = await api.enterBid(version.value, ctx.rfq, ctx.supplier, rates, bidValid.value, submit, ctx.revise)
    bidCtx.value = null // the bid is saved: close even if an upload below fails
    for (const file of files) await api.uploadTo('Supplier Quotation', response.result, file)
    return files.length ? { ...response, sourcing: await api.getSourcing(version.value) } : response
  }, (name) => `${ctx.revise ? 'Revised bid' : 'Bid'} ${name} saved for ${ctx.supplier}`)
}

// RFQ dialog
const rfqOpen = ref(false)
const suppliers = ref([])
const message = ref('')

async function sendRfq() {
  rfqOpen.value = false
  await act(() => api.sendRfq(version.value, [...selected.value], suppliers.value, message.value), (name) => `Created ${name}`)
  selected.value = new Set()
  suppliers.value = []
}
</script>
