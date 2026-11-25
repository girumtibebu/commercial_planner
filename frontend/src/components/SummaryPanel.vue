<template>
  <div class="grid gap-3">
    <!-- before winning: price, estimate, profit, margin (vs the last round sent);
         after winning: the agreed budget and what has been ordered and spent against it -->
    <div class="grid grid-cols-2 gap-3" :class="summary.won ? 'lg:grid-cols-5' : 'lg:grid-cols-4'">
      <div class="cp-stat">
        <span class="cp-stat-label">Client price</span>
        <span class="cp-stat-value">{{ fmt.money(summary.selling) }}</span>
        <span class="cp-stat-sub">{{ summary.selling ? 'From the linked document' : 'No client price yet' }}</span>
      </div>
      <template v-if="!summary.won">
        <div class="cp-stat">
          <span class="cp-stat-label">Estimate</span>
          <span class="cp-stat-value">{{ fmt.money(summary.estimate) }}</span>
          <span class="cp-stat-sub">{{ reference ? `${signed(summary.estimate - reference.cost)} vs ${reference.label}` : 'Cost of this plan' }}</span>
        </div>
        <div class="cp-stat">
          <span class="cp-stat-label">Profit</span>
          <span class="cp-stat-value" :class="tone(summary.profit)">{{ fmt.money(summary.profit) }}</span>
          <span class="cp-stat-sub">Client price − estimate</span>
        </div>
        <div class="cp-stat">
          <span class="cp-stat-label">Margin</span>
          <span class="cp-stat-value" :class="tone(summary.margin)">{{ fmt.percent(summary.margin) }}</span>
          <span class="cp-stat-sub">{{ reference ? `${reference.label}: ${fmt.percent(reference.margin)}` : 'Profit ÷ client price' }}</span>
        </div>
      </template>
      <template v-else>
        <div class="cp-stat">
          <span class="cp-stat-label">Agreed budget</span>
          <span class="cp-stat-value">{{ fmt.money(summary.agreed) }}</span>
          <span class="cp-stat-sub">
            Estimate {{ fmt.money(summary.estimate) }} ({{ signed(summary.estimate - summary.agreed) }})<template v-if="agreedVariations"> · incl. {{ agreedVariations }} variation{{ agreedVariations > 1 ? 's' : '' }}</template>
          </span>
        </div>
        <div class="cp-stat">
          <span class="cp-stat-label">Ordered</span>
          <span class="cp-stat-value">{{ fmt.money(summary.ordered) }}</span>
          <span class="cp-stat-sub">On POs, not yet invoiced</span>
        </div>
        <div class="cp-stat">
          <span class="cp-stat-label">Spent</span>
          <span class="cp-stat-value">{{ fmt.money(summary.spent) }}</span>
          <span class="cp-stat-sub">Invoiced, settled, project costs</span>
        </div>
        <div class="cp-stat">
          <span class="cp-stat-label">Left</span>
          <span class="cp-stat-value" :class="tone(summary.left)">{{ fmt.money(summary.left) }}</span>
          <span class="cp-stat-sub">Agreed − ordered − spent</span>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ summary: Object, fmt: Object })

const reference = computed(() => props.summary.reference)
const agreedVariations = computed(() => Object.values(props.summary.variations || {}).filter((v) => v.docstatus === 1).length)
const signed = (value) => props.fmt.signed(value || 0)
const tone = (value) => (value == null ? 'text-ink-gray-5' : value < 0 ? '!text-ink-red-6' : value > 0 ? '!text-ink-green-8' : '')
</script>
