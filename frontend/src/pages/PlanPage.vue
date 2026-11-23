<template>
  <PageFrame subtitle="Build the internal cost behind each quotation item, compare versions, and watch the margin.">
    <VersionBar :focus="focusVersion" :can-write="Boolean(ws.plan.can_write)" :won="Boolean(ws.summary?.won)" @new-version="(name) => openCreate(name)" />

    <div
      v-if="ws.plan.created_from === 'Project' && !ws.plan.sales_order"
      class="rounded-lg border border-outline-blue-1 bg-surface-blue-2 px-4 py-2 text-sm text-ink-blue-8"
    >
      This project has no Sales Order, so there is no client selling price to compare against — costs only.
    </div>

    <SyncBanner
      :status="ws.sync[focusVersion?.name]"
      :editable="Boolean(focusVersion?.can_edit)"
      :source="focusVersion?.source_name || 'the document'"
      :synced="Boolean(focusVersion?.syncs_quotation)"
      :fmt="fmt"
      class="overflow-hidden rounded-lg border"
      @sync="syncNow"
      @newversion="openCreate(focusVersion.name, true)"
      @add="send(focusVersion.name, [{ op: 'sync_source' }])"
      @refresh="send(focusVersion.name, [{ op: 'refresh_source' }])"
    />

    <SummaryPanel :summary="ws.summary" :fmt="fmt" />

    <div class="flex min-h-[420px] flex-1 flex-col overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base">
      <Toolbar
        :editable="Boolean(focusVersion?.can_edit)"
        :grid="grid"
        :actuals="Boolean(ws.plan.sales_order || ws.plan.project)"
        :refreshing="refreshing"
        @refresh-actuals="refreshActuals"
      />
      <div class="min-h-0 flex-1">
        <SheetGrid ref="grid" :ws="ws" :focus="focusVersion" :fmt="fmt" :send="send" :set-item-field="setItemField" @details="openDetails" />
      </div>
    </div>

    <LineDetailsDialog
      v-model="detailsOpen"
      :row="detailsRow"
      :version="focusVersion?.name"
      :editable="Boolean(focusVersion?.can_edit)"
      @save="saveDetails"
    />
  </PageFrame>
</template>

<script setup>
import PageFrame from '../components/PageFrame.vue'
import { inject, onBeforeUnmount, onMounted, ref } from 'vue'
import { toast } from 'frappe-ui'
import { api } from '../api'
import { readError } from '../useWorkspace'
import LineDetailsDialog from '../components/LineDetailsDialog.vue'
import SheetGrid from '../components/SheetGrid.vue'
import SummaryPanel from '../components/SummaryPanel.vue'
import SyncBanner from '../components/SyncBanner.vue'
import Toolbar from '../components/Toolbar.vue'
import VersionBar from '../components/VersionBar.vue'

const { ws, planName, fmt, focusVersion, send, setItemField, load, openCreate } = inject('cp')

const grid = ref(null)
const detailsOpen = ref(false)
const detailsRow = ref(null)
const refreshing = ref(false)

async function refreshActuals() {
  refreshing.value = true
  try {
    await api.refreshActuals(planName)
    await load()
    toast.success('Actual and committed cost refreshed')
  } catch (err) {
    toast.error(readError(err))
  } finally {
    refreshing.value = false
  }
}

function openDetails(row) {
  detailsRow.value = row
  detailsOpen.value = true
}

function saveDetails({ row_key, values }) {
  send(focusVersion.value.name, [{ op: 'update', row_key, values }])
}

/** A draft Quotation's changes are shown in the banner; they are taken into the plan only on Sync now. */
async function syncNow() {
  try {
    await api.syncQuotation(focusVersion.value.name)
    await load()
    toast.success('Plan synced with the Quotation')
  } catch (err) {
    toast.error(readError(err))
  }
}

// Live: check for Quotation changes every 30 seconds, so a change made in Desk shows here without a reload.
let syncTimer = null
async function checkSync() {
  try {
    if (ws.value) ws.value.sync = await api.getSyncStatus(planName)
  } catch {
    // try again at the next check
  }
}
onMounted(() => (syncTimer = setInterval(checkSync, 30000)))
onBeforeUnmount(() => clearInterval(syncTimer))
</script>
