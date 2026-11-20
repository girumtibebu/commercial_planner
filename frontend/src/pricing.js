/** Pricing vocabulary shared by the cost plan and Sourcing.
 *  A top-level category sets the CLIENT price; a cost line says where its COST comes from. */
export const COST_FROM = [
  { value: 'Manual', label: 'Manual', hint: 'An estimate you type into Unit cost', tone: 'bg-surface-gray-2 text-ink-gray-7', dot: 'bg-surface-gray-7' },
  { value: 'LTA', label: 'LTA', hint: 'Fixed agreed price, filled from the LTA price list', tone: 'bg-surface-green-2 text-ink-green-8', dot: 'bg-surface-green-7' },
  {
    value: 'Requirement',
    label: 'Quote (RFQ)',
    hint: 'Priced only by the supplier bid you pick in Sourcing',
    tone: 'bg-surface-amber-2 text-ink-amber-8',
    dot: 'bg-surface-amber-7',
  },
]

/** Cost lines say where their cost comes from; client prices are typed (Rate). */
export function pricingFor(row) {
  if (row.row_type === 'Cost Item') return { field: 'pricing_basis', options: COST_FROM, title: 'Cost from' }
  return null
}
