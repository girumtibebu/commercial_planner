/** Ready column views for the cost plan; the user's own adjustments start from one of these. */
export const VIEWS = {
  Commercial: ['description', 'qty', 'days', 'rate', 'selling', 'margin'],
  Costing: ['description', 'qty', 'days', 'unit_cost', 'cost', 'supplier', 'basis', 'delta'],
  'After win': ['description', 'cost', 'ordered', 'spent', 'left'],
}
