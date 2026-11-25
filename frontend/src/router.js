import { h } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'

const PlanPage = () => import('./pages/PlanPage.vue')
const VersionsPage = () => import('./pages/VersionsPage.vue')
const ActivityPage = () => import('./pages/ActivityPage.vue')
const CommentsPage = () => import('./pages/CommentsPage.vue')
const DetailsPage = () => import('./pages/DetailsPage.vue')
const SourcingPage = () => import('./pages/SourcingPage.vue')

export const PAGES = [
  { key: 'plan', label: 'Cost plan', icon: 'lucide-table-2' },
  { key: 'sourcing', label: 'Sourcing', icon: 'lucide-truck' },
  { key: 'versions', label: 'Versions', icon: 'lucide-layers' },
  { key: 'activity', label: 'Activity', icon: 'lucide-history' },
  { key: 'comments', label: 'Comments', icon: 'lucide-message-square' },
  { key: 'details', label: 'Details', icon: 'lucide-info' },
]

export default createRouter({
  history: createWebHistory('/commercial-planning'),
  routes: [
    { path: '/plan/:plan', redirect: (to) => `/plan/${to.params.plan}/plan` },
    { path: '/plan/:plan/plan', name: 'plan', component: PlanPage },
    { path: '/plan/:plan/sourcing', name: 'sourcing', component: SourcingPage },
    { path: '/plan/:plan/versions', name: 'versions', component: VersionsPage },
    { path: '/plan/:plan/activity', name: 'activity', component: ActivityPage },
    { path: '/plan/:plan/comments', name: 'comments', component: CommentsPage },
    { path: '/plan/:plan/details', name: 'details', component: DetailsPage },
    // no redirect here: there is no page at '/', so redirecting into this route loops forever
    { path: '/:pathMatch(.*)*', component: { render: () => h('p', { class: 'm-6 text-sm text-ink-gray-6' }, 'Page not found. Open a plan from its Quotation, Sales Order or Project.') } },
  ],
})
