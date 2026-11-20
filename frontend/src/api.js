import { call } from 'frappe-ui'

const PREFIX = 'commercial_planning.api.'

const json = (value) => (value == null ? undefined : JSON.stringify(value))

export const api = {
  getWorkspace: (plan, versions) =>
    call(PREFIX + 'planning.get_workspace', { plan, versions: json(versions) }),

  applyOps: (version, ops, expectedModified, versions) =>
    call(PREFIX + 'planning.apply_ops', {
      version,
      ops: JSON.stringify(ops),
      expected_modified: expectedModified,
      versions: json(versions),
    }),

  createVersion: (args, versions) =>
    call(PREFIX + 'version.create', { ...args, versions: json(versions) }),
  getPanel: (doctype, name) => call(PREFIX + 'panels.get_panel', { doctype, name }),
  savePanel: (doctype, name, values, modified) => call(PREFIX + 'panels.save_panel', { doctype, name, values: JSON.stringify(values), modified }),
  runPanelAction: (doctype, name, action) => call(PREFIX + 'panels.run_action', { doctype, name, action }),
  submitRevision: (version, versions) => call(PREFIX + 'version.submit_revision', { version, versions: json(versions) }),
  approveRevision: (version, versions) => call(PREFIX + 'version.approve_revision', { version, versions: json(versions) }),
  rejectRevision: (version, reason, versions) => call(PREFIX + 'version.reject_revision', { version, reason, versions: json(versions) }),
  billToClient: (version, rows, versions) => call(PREFIX + 'version.bill_to_client', { version, rows: JSON.stringify(rows), versions: json(versions) }),
  saveColumns: (choice) => call(PREFIX + 'planning.save_columns', { choice: JSON.stringify(choice) }),
  setItemField: (version, rowKey, field, value, versions) =>
    call(PREFIX + 'planning.set_item_field', { version, row_key: rowKey, field, value, versions: json(versions) }),


  logView: (plan) => call(PREFIX + 'activity.log_view', { plan }),
  getActivity: (plan, version) => call(PREFIX + 'activity.get_activity', { plan, version: version || undefined }),
  getComments: (plan) => call(PREFIX + 'activity.get_comments', { plan }),
  addComment: (plan, content) => call(PREFIX + 'activity.add_comment', { plan, content }),
  deleteComment: (plan, comment) => call(PREFIX + 'activity.delete_comment', { plan, comment }),

  getDetails: (plan) => call(PREFIX + 'details.get_details', { plan }),
  assign: (plan, user) => call(PREFIX + 'details.assign', { plan, user }),
  unassign: (plan, user) => call(PREFIX + 'details.unassign', { plan, user }),
  addTag: (plan, tag) => call(PREFIX + 'details.add_tag', { plan, tag }),
  removeTag: (plan, tag) => call(PREFIX + 'details.remove_tag', { plan, tag }),
  shareWith: (plan, user, write) => call(PREFIX + 'details.share_with', { plan, user, write: write ? 1 : 0 }),
  unshare: (plan, user) => call(PREFIX + 'details.unshare', { plan, user }),
  removeAttachment: (plan, file) => call(PREFIX + 'details.remove_attachment', { plan, file }),

  upload: (plan, file) => api.uploadTo('Commercial Planning', plan, file),

  async uploadTo(doctype, docname, file) {
    const form = new FormData()
    form.append('file', file, file.name)
    form.append('is_private', '1')
    form.append('doctype', doctype)
    form.append('docname', docname)
    form.append('folder', 'Home/Attachments')
    const response = await fetch('/api/method/upload_file', {
      method: 'POST',
      body: form,
      credentials: 'include',
      headers: { 'X-Frappe-CSRF-Token': window.csrf_token },
    })
    if (!response.ok) throw new Error(`Upload failed (${response.status})`)
    return (await response.json()).message
  },

  getSourcing: (version) => call(PREFIX + 'sourcing.get_sourcing', { version }),
  refreshActuals: (plan) => call(PREFIX + 'actuals.refresh', { plan }),
  getQuotationState: (version) => call(PREFIX + 'sourcing.get_quotation_state', { version }),
  listSuppliers: () =>
    call('frappe.client.get_list', {
      doctype: 'Supplier',
      fields: ['name', 'supplier_name', 'supplier_group'],
      filters: { disabled: 0 },
      order_by: 'name asc',
      limit_page_length: 500,
    }),
  sendRfq: (version, rows, suppliers, message) =>
    call(PREFIX + 'sourcing.send_rfq', { version, rows: JSON.stringify(rows), suppliers: JSON.stringify(suppliers), message }),
  bidForm: (version, rfq, supplier, revise) => call(PREFIX + 'sourcing.bid_form', { version, rfq, supplier, revise: revise || null }),
  enterBid: (version, rfq, supplier, rates, validTill, submit, revise) =>
    call(PREFIX + 'sourcing.enter_bid', {
      version, rfq, supplier, rates: JSON.stringify(rates), valid_till: validTill || null, submit: submit ? 1 : 0, revise: revise || null,
    }),
  pullQuotes: (version) => call(PREFIX + 'sourcing.pull_quotes', { version }),
  selectQuote: (version, rowKey, supplierQuotation) =>
    call(PREFIX + 'sourcing.select_quote', { version, row_key: rowKey, supplier_quotation: supplierQuotation }),
  createPurchaseOrders: (version, submit, supplier) =>
    call(PREFIX + 'sourcing.create_purchase_orders', { version, submit: submit ? 1 : 0, supplier: supplier || null }),
  settleInternal: (version) => call(PREFIX + 'sourcing.settle_internal', { version }),

  getItemName: (item) =>
    call('frappe.client.get_value', { doctype: 'Item', fieldname: 'item_name', filters: item }).then((r) => r?.item_name),

  searchLink: (doctype, txt) =>
    call('frappe.desk.search.search_link', { doctype, txt: txt || '', page_length: 10 }),
}

export const deskUrl = (doctype, name) =>
  `/desk/${doctype.toLowerCase().replace(/ /g, '-')}/${encodeURIComponent(name)}`
