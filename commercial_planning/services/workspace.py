"""Read model for the Vue workspace: header, version columns, merged matrix and KPIs."""

import frappe
from frappe.utils import flt

from commercial_planning.services import columns as grid_columns
from commercial_planning.services import permissions, quote_sync, revisions
from commercial_planning.services import sync as sync_service

VERSION = "Commercial Planning Version"
IDENTITY = ("row_key", "parent_key", "row_type", "description")
VALUE_FIELDS = (
	"notes",
	"cost_type",
	"cost_source",
	"item_code",
	"supplier",
	"vendor_quote",
	"qty",
	"days",
	"pages",
	"rate",
	"off_quotation",
	"changed_in_quotation",
	"after_agreement",
	"variation_order",
	"uom",
	"unit_cost",
	"cost_currency",
	"exchange_rate",
	"adj_mode",
	"adj_percent",
	"cost_amount",
	"selling_amount",
	"pricing_basis",
	"cost_center",
	"rfq",
	"supplier_quotation",
	"purchase_order",
	"settlement",
)
VERSION_FIELDS = (
	"name",
	"version_no",
	"version_name",
	"stage",
	"purpose",
	"status",
	"lock_kind",
	"lock_reason",
	"round_no",
	"is_revision",
	"revision_status",
	"approval_reasons",
	"reject_reason",
	"reference_role",
	"template",
	"reason",
	"owner",
	"creation",
	"modified",
	"frozen_by",
	"frozen_on",
	"approved_by",
	"approved_on",
	"created_from_version",
	"source_doctype",
	"source_name",
	"total_selling",
	"total_cost",
	"total_profit",
	"margin_pct",
)
PLAN_FIELDS = (
	"name",
	"title",
	"customer",
	"company",
	"currency",
	"status",
	"current_stage",
	"quotation",
	"sales_order",
	"project",
)


def get_workspace(plan, versions=None):
	doc = frappe.get_doc("Commercial Planning", plan)
	doc.check_permission("read")
	all_versions = frappe.get_all(VERSION, filters={"planning": plan}, fields=list(VERSION_FIELDS), order_by="version_no asc")
	selected = pick_columns(doc, all_versions, versions)
	return {
		"plan": plan_header(doc),
		"versions": [describe_version(ver) for ver in all_versions],
		"columns": [column_for(ver) for ver in selected],
		"rows": merged_rows(selected),
		"sections": sections(selected),
		"grid_columns": {"available": grid_columns.available(), "chosen": grid_columns.chosen()},
		"actuals": actual_totals(doc, selected),
		"summary": summary(doc, all_versions),
		"sync": sync_status(selected),
		"templates": templates(),
		"stages": frappe.get_all("Commercial Version Stage", pluck="name", order_by="creation asc"),
		"purposes": frappe.get_all("Commercial Version Purpose", pluck="name", order_by="creation asc"),
	}


def sections(selected):
	"""{client row_key: section title}: each section row of a version's Quotation / Sales Order (emc_utils'
	is_section) heads the client line of the next item. The newest displayed version wins."""
	found = {}
	for ver in selected:
		child = f"{ver.source_doctype} Item"
		if not ver.source_name or not frappe.db.exists("DocType", child) or not frappe.get_meta(child).has_field("is_section"):
			continue
		items = frappe.get_all(
			child,
			{"parent": ver.source_name, "parenttype": ver.source_doctype},
			["name", "is_section", "section_title", "item_name"],
			order_by="idx asc",
		)
		row_of = {link.link_name: link.row_key for link in frappe.get_doc(VERSION, ver.name).item_links}
		pending = []
		for item in items:
			if item.is_section:
				pending.append(item.section_title or item.item_name)
			elif pending and item.name in row_of:
				found[row_of[item.name]] = " · ".join(pending)
				pending = []
	return found


def templates():
	return frappe.get_all(
		"Commercial Version Template",
		fields=["name", "version_name", "stage", "purpose", "copy_from", "reference_role", "freeze_source", "requires_approval", "trigger"],
		order_by="creation asc",
	)


def sync_status(selected):
	"""Per displayed version: differences from the document it is built on."""
	status = {}
	for ver in selected:
		found = sync_service.get_status(frappe.get_doc(VERSION, ver.name))
		if found:
			status[ver.name] = found
	return status


def reference_version(all_versions):
	"""The last number committed to the client: the Agreed budget once won, else the latest submitted round."""
	for kind in ("Agreed", "Round"):
		found = [ver for ver in all_versions if ver.lock_kind == kind]
		if found:
			return found[-1]
	return None


def pick_columns(doc, all_versions, requested):
	"""Requested versions; else the reference version (latest round / Agreed budget) plus the latest one."""
	by_name = {ver.name: ver for ver in all_versions}
	if requested:
		return [by_name[name] for name in requested if name in by_name]
	chosen = set()
	reference = reference_version(all_versions)
	if reference:
		chosen.add(reference.name)
	if all_versions:
		chosen.add(all_versions[-1].name)
	return sorted((by_name[name] for name in chosen), key=lambda ver: ver.version_no)


LINKED = (("Quotation", "quotation"), ("Sales Order", "sales_order"), ("Project", "project"))


def linked_documents(doc):
	"""The ERPNext documents this plan follows, with their current status."""
	found = []
	for doctype, field in LINKED:
		name = doc.get(field)
		if name:
			found.append({"doctype": doctype, "name": name, "status": frappe.db.get_value(doctype, name, "status")})
	return found


def plan_header(doc):
	header = {field: doc.get(field) for field in PLAN_FIELDS}
	header["can_write"] = bool(frappe.has_permission("Commercial Planning", "write", doc=doc))
	header["linked"] = linked_documents(doc)
	header["owner"] = doc.owner
	return header


def version_label(ver):
	return f"V{ver.version_no} {ver.version_name}"


def describe_version(ver):
	doc = frappe.get_doc(VERSION, ver.name)
	return dict(ver) | {
		"label": version_label(ver),
		"can_edit": permissions.can_edit_version(doc),
		# client lines and the draft Quotation are one: their fields are edited here only while this is true
		"syncs_quotation": bool(quote_sync.active_quotation(doc)),
		"can_approve": ver.revision_status == "Needs approval" and revisions.can_approve(),
	}


def column_for(ver):
	named = ver.lock_kind in ("Round", "Agreed")  # "Round 2", "Agreed budget" read better than "V4"
	return {
		"version": ver.name,
		"key": f"v{ver.version_no}",
		"label": version_label(ver),
		"short": ver.version_name if named else f"V{ver.version_no}",
		"role": None,
		"lock_kind": ver.lock_kind,
		"status": ver.status,
	}


def version_rows(name):
	fields = list(IDENTITY + VALUE_FIELDS)
	return frappe.get_all(
		"Commercial Planning Item",
		filters={"parent": name, "parenttype": VERSION},
		fields=fields,
		order_by="idx asc",
	)


def merged_rows(selected):
	"""Union of the rows of every selected version, joined by row_key, in tree order."""
	if not selected:
		return []
	priority = list(reversed(selected))
	per_version = {}
	children = {}
	fields = [col["key"] for col in grid_columns.item_fields()]
	for ver in priority:
		rows = version_rows(ver.name)
		doc = frappe.get_doc(VERSION, ver.name)
		linked = {link.row_key for link in doc.item_links}
		items = grid_columns.item_values(doc, fields)
		for row in rows:
			row.linked = row.row_key in linked
			row.item = items.get(row.row_key)
		per_version[ver.name] = {row.row_key: row for row in rows}
		children[ver.name] = {}
		for row in rows:
			children[ver.name].setdefault(row.parent_key or "", []).append(row.row_key)
	output = []
	walk("", 0, priority, per_version, children, output)
	return output


def merge_order(parent_key, priority, children):
	merged = []
	for ver in priority:
		siblings = children[ver.name].get(parent_key, [])
		for index, key in enumerate(siblings):
			if key in merged:
				continue
			previous = siblings[index - 1] if index else None
			if previous in merged:
				merged.insert(merged.index(previous) + 1, key)
			elif index == 0:
				merged.insert(0, key)
			else:
				merged.append(key)
	return merged


def walk(parent_key, depth, priority, per_version, children, output):
	for key in merge_order(parent_key, priority, children):
		holders = [ver for ver in priority if key in per_version[ver.name]]
		first = per_version[holders[0].name][key]
		output.append(
			{
				"row_key": key,
				"parent_key": parent_key,
				"depth": depth,
				"row_type": first.row_type,
				"description": first.description,
				"values": {ver.name: strip_identity(per_version[ver.name][key]) for ver in holders},
			}
		)
		walk(key, depth + 1, priority, per_version, children, output)


def strip_identity(row):
	return {field: row.get(field) for field in VALUE_FIELDS + ("linked", "item")}


def actual_totals(doc, selected):
	"""Actual/committed per row_key rolled up the newest selected tree; plus the unallocated bucket."""
	entries = frappe.db.sql(
		"""select row_key, basis, sum(amount) as amount from `tabCommercial Planning Actual`
		where planning=%s group by row_key, basis""",
		doc.name,
		as_dict=True,
	)
	result = {"rows": {}, "unallocated": {"Actual": 0, "Committed": 0}}
	parents = {}
	if selected:
		for row in version_rows(selected[-1].name):
			parents[row.row_key] = row.parent_key
	for entry in entries:
		key = entry.row_key
		if not key or key not in parents:
			result["unallocated"][entry.basis] += flt(entry.amount)
			continue
		while key:
			bucket = result["rows"].setdefault(key, {"Actual": 0, "Committed": 0})
			bucket[entry.basis] += flt(entry.amount)
			key = parents.get(key)
	return result


def summary(doc, all_versions):
	"""Price, Estimate (the newest version), the reference committed to the client, and the job's spending.

	Before winning the reference is the latest round; after, the Agreed budget, and Ordered / Spent / Left apply."""
	latest = all_versions[-1] if all_versions else None
	reference = reference_version(all_versions)
	won = bool(reference and reference.lock_kind == "Agreed")
	if won:  # after winning: the Estimate is the latest approved revision; a draft revision is shown on its own
		latest = next((v for v in reversed(all_versions) if v.revision_status == "Approved"), reference)
	selling = flt(latest.total_selling) if latest else 0
	estimate = flt(latest.total_cost) if latest else 0
	ordered = flt(
		frappe.db.sql(
			"select sum(amount) from `tabCommercial Planning Actual` where planning=%s and basis='Committed'", doc.name
		)[0][0]
	)
	spent = flt(doc.actual_cost)
	totals = revisions.agreed_totals(doc.name) if won else None
	agreed = totals["cost"] if totals else None
	if totals:
		selling = totals["price"]  # the original agreement plus agreed variations
	return {
		"selling": selling,
		"estimate": estimate,
		"profit": selling - estimate,
		"margin": (selling - estimate) / selling * 100 if selling else None,
		"won": won,
		"reference": {
			"name": reference.name,
			"label": reference.version_name,
			"kind": reference.lock_kind,
			"cost": flt(reference.total_cost),
			"selling": flt(reference.total_selling),
			"margin": flt(reference.margin_pct),
		}
		if reference
		else None,
		"agreed": agreed,
		"ordered": ordered,
		"spent": spent,
		"left": agreed - ordered - spent if won else None,
		"estimate_version": latest.name if latest else None,
		"variations": revisions.variations(doc.name) if won else {},
		"pending_revision": next((v.name for v in all_versions if v.revision_status == "Needs approval"), None),
		# what was offered at each round and what was agreed: the negotiation in numbers
		"history": [
			{
				"name": ver.name,
				"label": ver.version_name,
				"kind": ver.lock_kind,
				"selling": flt(ver.total_selling),
				"cost": flt(ver.total_cost),
				"margin": flt(ver.margin_pct),
			}
			for ver in all_versions
			if ver.lock_kind in ("Round", "Agreed")
		],
	}
