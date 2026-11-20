<template>
  <div class="flex h-full overflow-hidden bg-surface-base text-ink-gray-8">
    <div v-if="isMobile && drawerOpen" class="fixed inset-0 z-40 bg-black/50 backdrop-blur-xs" @click="drawerOpen = false" />

    <!-- Sidebar on desktop and tablet, slide-over drawer on mobile -->
    <aside
      class="flex h-full shrink-0 border-r border-outline-gray-1 transition-transform duration-200"
      :class="[isMobile ? 'fixed inset-y-0 left-0 z-50 shadow-2xl' : '', isMobile && !drawerOpen ? '-translate-x-full' : '']"
    >
      <Sidebar v-model:collapsed="collapsed" :disable-collapse="isMobile">
        <div class="px-2">
          <SidebarHeader title="Commercial Planning" :subtitle="ws?.plan.title || userLabel" :logo="LOGO" :menu-items="appMenu" />
        </div>

        <div class="flex-1 overflow-y-auto overflow-x-hidden px-2 pt-1">
          <div v-if="ws && (!collapsed || isMobile)" class="mt-2 flex flex-col gap-2">
            <SidebarLabel divider>Linked documents</SidebarLabel>
            <button
              v-for="doc in ws.plan.linked"
              :key="doc.doctype + doc.name"
              class="group rounded-xl border bg-surface-base px-3 py-2.5 text-left shadow-2xs transition-colors hover:border-outline-gray-4"
              :class="isOrigin(doc) ? 'border-outline-blue-3' : 'border-outline-gray-2'"
              @click="openDoc(doc)"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="text-xs text-ink-gray-5">{{ doc.doctype }}</span>
                <span class="lucide-external-link size-3 text-ink-gray-4 group-hover:text-ink-gray-7" />
              </div>
              <div class="mt-0.5 truncate font-mono text-xs text-ink-gray-9">{{ doc.name }}</div>
              <div class="mt-1.5 flex items-center gap-1.5">
                <Badge v-if="doc.status" :label="doc.status" theme="gray" size="sm" />
                <Badge v-if="isOrigin(doc)" label="Opened from" theme="blue" size="sm" />
              </div>
            </button>
            <div v-if="!ws.plan.linked.length" class="px-2 text-xs text-ink-gray-5">Nothing linked yet.</div>
          </div>
        </div>

        <div class="mt-auto flex flex-col gap-0.5 px-2 pb-2">
          <SidebarItem label="Back to Desk" icon="lucide-arrow-left" @click="goToDesk" />
          <SidebarCollapseToggle v-if="!isMobile" />
        </div>
      </Sidebar>
    </aside>

    <div class="flex min-w-0 flex-1 flex-col">
      <!-- 48px top bar lines up with the sidebar header -->
      <header class="flex h-12 shrink-0 items-center gap-2 border-b border-outline-gray-1 bg-surface-base px-3 sm:px-5">
        <button
          v-if="isMobile"
          class="flex h-8 w-8 items-center justify-center rounded-md text-ink-gray-7 active:bg-surface-gray-2"
          @click="drawerOpen = !drawerOpen"
        >
          <span class="lucide-menu size-4" />
        </button>

        <Breadcrumbs :items="crumbs" class="min-w-0" />

        <div class="ml-auto flex items-center gap-2">
          <QuotationActions v-if="ws" />
          <template v-if="ws">
            <span
              v-if="ws.columns.length > 1"
              class="hidden items-center gap-1 rounded-md bg-surface-gray-2 px-2 py-1 text-xs text-ink-gray-7 md:flex"
            >
              <span class="lucide-columns-2 size-3" /> Comparing {{ ws.columns.length }}
            </span>
            <VersionSwitcher />
            <Button variant="solid" :disabled="!ws.plan.can_write" @click="openCreate(null)">
              <template #prefix><span class="lucide-plus size-4" /></template>
              <span class="hidden sm:inline">New version</span>
            </Button>
          </template>
        </div>
      </header>

      <!-- Page tabs, as in Frappe CRM -->
      <nav class="no-scrollbar flex h-11 shrink-0 items-stretch gap-1 overflow-x-auto border-b border-outline-gray-1 bg-surface-base px-3 sm:px-5">
        <router-link
          v-for="page in PAGES"
          :key="page.key"
          :to="{ name: page.key, params: { plan: planName } }"
          class="relative flex shrink-0 items-center gap-1.5 px-2.5 text-base"
          :class="route.name === page.key ? 'font-medium text-ink-gray-9' : 'text-ink-gray-5 hover:text-ink-gray-8'"
          :aria-current="route.name === page.key ? 'page' : undefined"
        >
          <span v-if="route.name === page.key" class="absolute inset-x-1 bottom-0 h-0.5 rounded-full bg-surface-gray-7" />
          <span :class="page.icon" class="size-4" />
          {{ page.label }}
          <span v-if="counts[page.key]" class="rounded-full bg-surface-gray-3 px-1.5 text-xs text-ink-gray-6">{{ counts[page.key] }}</span>
        </router-link>
      </nav>

      <main class="flex min-h-0 flex-1 flex-col overflow-hidden"><slot /></main>
    </div>

    <Dialog v-model="aboutOpen" title="About">
      <div class="flex items-center gap-3">
        <img :src="LOGO" class="size-10 rounded-md" alt="" />
        <div>
          <div class="text-base-medium text-ink-gray-9">Commercial Planning</div>
          <div class="text-sm text-ink-gray-5">Cost plans that follow a job from quotation to project.</div>
        </div>
      </div>
    </Dialog>
  </div>
</template>

<script setup>
import { computed, h, inject, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  Badge,
  Breadcrumbs,
  Button,
  Dialog,
  Sidebar,
  SidebarCollapseToggle,
  SidebarHeader,
  SidebarItem,
  SidebarLabel,
  call,
  createResource,
  useTheme,
} from 'frappe-ui'
import QuotationActions from './QuotationActions.vue'
import VersionSwitcher from './VersionSwitcher.vue'
import { PAGES } from '../router'

const { ws, planName, origin, saving, goToDesk, deskPath, openCreate, openPanel } = inject('cp')
const route = useRoute()

const LOGO = '/assets/commercial_planning/images/commercial_planning.svg'
const userLabel = window.user_fullname || window.user || 'You'

const drawerOpen = ref(false)
const aboutOpen = ref(false)
const isMobile = ref(false)
// Tablets start on the icon rail; the collapse toggle changes it after that.
const collapsed = ref(window.innerWidth < 1100)

function check() {
  isMobile.value = window.innerWidth < 768
}
onMounted(() => {
  check()
  window.addEventListener('resize', check)
})
onBeforeUnmount(() => window.removeEventListener('resize', check))

const isOrigin = (doc) => origin.doctype === doc.doctype && origin.name === doc.name
const counts = computed(() => ({ versions: ws.value?.versions.length || 0 }))
const openDoc = (doc) => openPanel(doc.doctype, doc.name)

const crumbs = computed(() => {
  const page = PAGES.find((item) => item.key === route.name)
  return [
    { label: ws.value?.plan.title || planName, route: { name: 'plan', params: { plan: planName } } },
    ...(page && page.key !== 'plan' ? [{ label: page.label }] : []),
  ]
})

// Theme is shared with Desk: start from the user's Desk theme and save changes back to it.
const DESK_THEME = { light: 'Light', dark: 'Dark', system: 'Automatic' }
const { currentTheme, setTheme } = useTheme()
setTheme({ Light: 'light', Dark: 'dark', Automatic: 'system' }[window.desk_theme] || currentTheme.value)
const theme = computed({
  get: () => currentTheme.value,
  set: (value) => {
    setTheme(value)
    call('frappe.core.doctype.user.user.switch_theme', { theme: DESK_THEME[value] })
  },
})

// Same source as the Frappe apps screen, so the switcher lists what this user can open.
const apps = createResource({ url: 'frappe.apps.get_apps', auto: true, initialData: [] })
const appIcon = (src) => () => h('img', { src, class: 'size-4 rounded-sm object-cover', alt: '' })

const appMenu = computed(() => [
  {
    group: 'App',
    hideLabel: true,
    options: [
      {
        label: 'Apps',
        icon: 'lucide-layout-grid',
        submenu: [
          { label: 'Desk', icon: 'lucide-box', onClick: () => (window.location.href = '/desk') },
          ...apps.data.map((app) => ({
            label: app.title,
            icon: app.logo ? appIcon(app.logo) : 'lucide-box',
            onClick: () => (window.location.href = app.route),
          })),
        ],
      },
      {
        label: 'Toggle Theme',
        icon: currentTheme.value === 'dark' ? 'lucide-sun' : 'lucide-moon',
        onClick: () => (theme.value = currentTheme.value === 'dark' ? 'light' : 'dark'),
      },
    ],
  },
  {
    group: 'Help',
    hideLabel: true,
    options: [
      {
        label: 'Help',
        icon: 'lucide-circle-help',
        submenu: [
          { label: 'About', icon: 'lucide-info', onClick: () => (aboutOpen.value = true) },
          ...(window.help_links || []).map((link) => ({
            label: link.label,
            icon: 'lucide-external-link',
            onClick: () => window.open(link.route, '_blank'),
          })),
        ],
      },
    ],
  },
  { group: 'Account', hideLabel: true, options: [{ label: 'Log out', icon: 'lucide-log-out', onClick: logout }] },
])

async function logout() {
  await call('logout')
  window.location.href = '/login'
}
</script>
