"""Actual and Committed cost of a plan, read from ERPNext (v2).

Versions are plans (what we expect to spend); actuals are what really happened, one stream per plan:
- Committed: a submitted Purchase Order raised from a plan line, less what is already invoiced or settled.
- Actual: a Purchase Invoice against that PO (external vendor), the settlement Journal Entry of a division
  line, and any other expense booked to the plan's Project (unallocated: not tied to a line).
Entries written here carry provider "erpnext" and are rebuilt on every sync; manual entries are kept."""

import frappe
from frappe.utils import flt, nowdate

PLAN = "Commercial Planning"
VERSION = "Commercial Planning Version"
ACTUAL = "Commercial Planning Actual"
PROVIDER = "erpnext"


def ordered_lines(plan_name):
	"""Lines that reached a PO, one per (PO, row_key), taken from the newest version that has them."""
	versions = frappe.get_all(VERSION, {"planning": plan_name}, pluck="name", order_by="version_no desc")
	if not versions:
		return []
	rows = frappe.get_all(
		"Commercial Planning Item",
		{"parenttype": VERSION, "parent": ["in", versions], "purchase_order": ["is", "set"]},
		["parent", "row_key", "description", "purchase_order", "po_item", "settlement", "cost_amount"],
	)
	rank = {name: index for index, name in enumerate(versions)}
	seen = {}
	for row in sorted(rows, key=lambda r: rank[r.parent]):
		seen.setdefault((row.purchase_order, row.row_key), row)
	return list(seen.values())


def line_shares(po, lines):
	"""Each line's part of the PO: its own PO row when known, else a share by planned cost."""
	by_item = {item.name: flt(item.base_net_amount) for item in po.items}
	unmatched = [line for line in lines if line.po_item not in by_item]
	rest = flt(po.base_net_total) - sum(by_item[line.po_item] for line in lines if line.po_item in by_item)
	planned = sum(flt(line.cost_amount) for line in unmatched) or len(unmatched) or 1
	shares = {}
	for line in lines:
		if line.po_item in by_item:
			shares[line.row_key] = by_item[line.po_item]
		else:  # shortcut: lines from before po_item was stored are split by planned cost; exact once re-ordered
			shares[line.row_key] = rest * (flt(line.cost_amount) or 1) / planned
	return shares


def invoiced(po):
	"""{po_item: invoiced amount} plus the invoices, from submitted Purchase Invoices against the PO."""
	rows = frappe.db.sql(
		"""select i.po_detail, i.base_net_amount, i.parent, p.posting_date
		from `tabPurchase Invoice Item` i join `tabPurchase Invoice` p on p.name = i.parent
		where i.purchase_order = %s and p.docstatus = 1""",
		po.name,
		as_dict=True,
	)
	amounts = {}
	for row in rows:
		amounts[row.po_detail] = amounts.get(row.po_detail, 0) + flt(row.base_net_amount)
	return amounts, rows


def entries_for(plan):
	entries, counted = [], set()
	lines = ordered_lines(plan.name)
	for po_name in sorted({line.purchase_order for line in lines}):
		po = frappe.get_doc("Purchase Order", po_name)
		if po.docstatus != 1:
			continue  # a draft commits nothing; a cancelled PO is gone
		mine = [line for line in lines if line.purchase_order == po_name]
		shares = line_shares(po, mine)
		billed, invoices = invoiced(po)
		billed_total = sum(billed.values())
		counted.update(row.parent for row in invoices)
		po_rows = {item.name for item in po.items}
		for line in mine:
			share = shares[line.row_key]
			settled = line.settlement and frappe.db.get_value("Journal Entry", line.settlement, "docstatus") == 1
			if settled:  # division work: the internal transfer is the actual cost
				counted.add(line.settlement)
				entries.append(entry(plan, line.row_key, "Actual", share, "Journal Entry", line.settlement, line.description))
				continue
			if line.po_item in po_rows:
				done = flt(billed.get(line.po_item))
			else:
				done = billed_total * share / (flt(po.base_net_total) or 1)
			if done:
				entries.append(entry(plan, line.row_key, "Actual", done, "Purchase Invoice", invoices[0].parent, line.description, po_name))
			if po.status != "Closed" and share - done > 0.005:
				entries.append(entry(plan, line.row_key, "Committed", share - done, "Purchase Order", po_name, line.description))
	entries.extend(project_costs(plan, counted))
	return entries


def project_costs(plan, counted):
	"""Other expenses booked to the plan's Project (timesheets, expense claims, stock issues…): unallocated."""
	if not plan.project:
		return []
	rows = frappe.db.sql(
		"""select g.voucher_type, g.voucher_no, max(g.posting_date) as posting_date, sum(g.debit - g.credit) as amount
		from `tabGL Entry` g join `tabAccount` a on a.name = g.account
		where g.project = %s and g.is_cancelled = 0 and a.root_type = 'Expense'
		group by g.voucher_type, g.voucher_no""",
		plan.project,
		as_dict=True,
	)
	return [
		entry(plan, None, "Actual", row.amount, row.voucher_type, row.voucher_no, f"{row.voucher_type} {row.voucher_no}", date=row.posting_date)
		for row in rows
		if row.voucher_no not in counted and abs(flt(row.amount)) > 0.005
	]


def entry(plan, row_key, basis, amount, doctype, name, description, detail=None, date=None):
	return {
		"doctype": ACTUAL,
		"planning": plan.name,
		"row_key": row_key,
		"basis": basis,
		"amount": flt(amount, 2),
		"currency": plan.currency,
		"posting_date": date or nowdate(),
		"description": description,
		"is_manual": 0,
		"provider": PROVIDER,
		"source_doctype": doctype,
		"source_name": name,
		"source_detail": detail,
	}


def sync(plan_name):
	"""Rebuild the ERPNext-sourced entries of one plan and its actual cost total."""
	plan = frappe.get_doc(PLAN, plan_name)
	frappe.db.delete(ACTUAL, {"planning": plan_name, "provider": PROVIDER})
	for values in entries_for(plan):
		frappe.get_doc(values).insert(ignore_permissions=True)
	total = frappe.db.sql(
		"select sum(amount) from `tabCommercial Planning Actual` where planning=%s and basis='Actual'", plan_name
	)[0][0]
	frappe.db.set_value(PLAN, plan_name, "actual_cost", flt(total), update_modified=False)


# ------------------------------------------------------- which plans to sync
def plans_for_orders(orders):
	if not orders:
		return set()
	versions = frappe.get_all("Commercial Planning Item", {"parenttype": VERSION, "purchase_order": ["in", list(orders)]}, pluck="parent")
	return set(frappe.get_all(VERSION, {"name": ["in", versions]}, pluck="planning")) if versions else set()


def plans_for_document(doc):
	"""Plans touched by a submitted/cancelled PO, Purchase Invoice or Journal Entry."""
	if doc.doctype == "Purchase Order":
		return plans_for_orders({doc.name})
	if doc.doctype == "Purchase Invoice":
		return plans_for_orders({item.purchase_order for item in doc.items if item.get("purchase_order")})
	plans = set()
	if doc.doctype == "Journal Entry":
		versions = frappe.get_all("Commercial Planning Item", {"parenttype": VERSION, "settlement": doc.name}, pluck="parent")
		if versions:
			plans |= set(frappe.get_all(VERSION, {"name": ["in", versions]}, pluck="planning"))
	projects = {row.get("project") for row in doc.get("accounts") or doc.get("items") or [] if row.get("project")}
	if doc.get("project"):
		projects.add(doc.project)
	if projects:
		plans |= set(frappe.get_all(PLAN, {"project": ["in", list(projects)]}, pluck="name"))
	return plans


def sync_for_document(doc):
	for plan_name in plans_for_document(doc):
		sync(plan_name)
