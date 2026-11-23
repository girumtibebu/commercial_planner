"""Two-way sync between a draft Quotation and its plan's client lines (v2, phase 2).

While the Quotation is a draft (not in review) and its version is editable, a client line (top-level
Category) and its Quotation Item are one thing edited from two places: planner edits are written to the
Quotation at once, and a Quotation saved in Desk updates the plan. Cost lines never reach the Quotation.

Quantities follow production's item fields when the site has them: Quantity x Number of Days x Number of
Pages = ERPNext qty, and rate is the price per unit per day. Section and alternative rows are left alone.
"""

import frappe
from frappe import _
from frappe.utils import flt

from commercial_planning.services import lifecycle, selling

VERSION = "Commercial Planning Version"
ITEM = "Quotation Item"
CATEGORY = "Category"
UNIT_FIELDS = ("quantity", "number_of_days", "number_of_pages")


def has_unit_fields(doctype):
	meta = frappe.get_meta(doctype)
	return all(meta.has_field(field) for field in UNIT_FIELDS)


def factor(row):
	"""Days x pages of a plan row (empty means 1)."""
	return (flt(row.get("days")) or 1) * (flt(row.get("pages")) or 1)


def units_from_item(item, doctype):
	"""qty, days, pages of a document item. Without the custom fields, ERPNext qty is the quantity."""
	if has_unit_fields(doctype) and flt(item.get("quantity")):
		qty, days, pages = flt(item.quantity), flt(item.number_of_days) or 1, flt(item.number_of_pages) or 1
		if abs(qty * days * pages - flt(item.get("qty"))) < 0.0005:
			return qty, days, pages
		# made without Desk's script (API, mapping): the fields were left at their defaults, so qty is the truth
	return flt(item.get("qty")), 1, 1


def units_to_item(row, doctype):
	qty = flt(row.qty) or 1
	values = {"qty": qty * factor(row)}
	if has_unit_fields(doctype):
		values.update(quantity=qty, number_of_days=flt(row.days) or 1, number_of_pages=flt(row.pages) or 1)
	return values


def check_client_lines_untouched(version, ops):
	"""Client lines follow the draft Quotation: the planner adds, moves and changes cost lines under them only."""
	top = {row.row_key for row in version.items if row.row_type == CATEGORY and not row.parent_key}
	for op in ops:
		kind, row_key = op.get("op"), op.get("row_key")
		if (kind == "add" or kind == "move") and not op.get("parent_key"):
			frappe.throw(_("Client lines follow the Quotation: add them there, then Sync here"))
		if kind in ("update", "move", "delete") and row_key in top:
			frappe.throw(_("Client lines follow the Quotation: change them there, then Sync here"))


def is_line_item(item):
	"""Section headers and alternatives are not client lines."""
	return not item.get("is_section") and not item.get("is_alternative")


# ------------------------------------------------------------------ when sync runs
def active_quotation(version):
	"""The draft Quotation this version syncs with, or None."""
	if version.status != "Working" or version.source_doctype != "Quotation" or not version.source_name:
		return None
	quotation = frappe.get_doc("Quotation", version.source_name)
	if quotation.docstatus != 0 or lifecycle.in_review(quotation):
		return None
	return quotation


def client_lines(version):
	return [row for row in version.items if row.row_type == CATEGORY and not row.parent_key]


def single_link(version, row):
	"""The one Quotation Item this client line owns fully, or None (split links are not synced)."""
	links = [link for link in version.item_links if link.row_key == row.row_key and link.link_doctype == ITEM]
	if len(links) == 1 and flt(links[0].allocation_pct) == 100:
		return links[0]
	return None


# ------------------------------------------------------------------ Quotation -> planner
def pull(quotation):
	"""A draft Quotation was saved in Desk: bring its items into the plan's editable version."""
	if quotation.flags.from_planner or quotation.docstatus != 0:
		return
	version = lifecycle.bound_version("Quotation", quotation.name)
	if not version or version.status != "Working":
		return
	from commercial_planning.services import tree
	from commercial_planning.services import version as version_service

	view = tree.Tree(version)
	live = [item for item in quotation.items if is_line_item(item)]
	live_names = {item.name for item in live}
	rows = {row.row_key: row for row in version.items}
	linked = {}
	for link in version.item_links:
		if link.link_doctype == ITEM:
			linked.setdefault(link.link_name, []).append(link.row_key)
	marked = {row.row_key for row in version.items if row.changed_in_quotation}
	for row in version.items:
		row.changed_in_quotation = 0
	before = [row.row_key for row in view.siblings("")]
	dirty = False
	order = []
	for item in live:
		keys = linked.get(item.name)
		if not keys:
			category, line = version_service.add_source_item(version, ITEM, item)
			view.rows[category.row_key] = category
			view.rows[line.row_key] = line
			view.siblings("").append(category)
			view.siblings(category.row_key).append(line)
			category.changed_in_quotation = 1
			order.append(category)
			dirty = True
			continue
		category = rows.get(keys[0])
		if category is None:
			continue
		if len(keys) == 1 and update_from_item(view, category, item):
			category.changed_in_quotation = 1
			dirty = True
		if category.off_quotation:
			category.off_quotation, category.changed_in_quotation, dirty = 0, 1, True
		order.append(category)
	gone = [link for link in version.item_links if link.link_doctype == ITEM and link.link_name not in live_names]
	for link in gone:
		row = rows.get(link.row_key)
		if row is not None:
			row.off_quotation = 1
			row.changed_in_quotation = 1
		dirty = True
	if gone:  # the item no longer exists, so the link cannot be kept; the greyed line keeps its cost work
		version.item_links = [link for link in version.item_links if link not in gone]
	rest = [row for row in view.siblings("") if row not in order]
	view.children[""] = order + rest  # plan follows the Quotation's order; lines it does not hold go last
	if not dirty and [row.row_key for row in view.children[""]] == before:
		for row in version.items:  # nothing new: keep the earlier "updated in Quotation" marks as they were
			row.changed_in_quotation = int(row.row_key in marked)
		return
	view.flush()
	selling.refresh_selling(version)
	tree.recalculate(version)
	version.flags.ignore_permissions = True
	version.save()


def update_from_item(view, category, item):
	"""Copy the client fields of `item` onto its client line; the first cost line follows untouched values."""
	qty, days, pages = units_from_item(item, ITEM)
	incoming = {
		"description": item.item_name or item.item_code,
		"item_code": item.item_code,
		"qty": qty,
		"days": days,
		"pages": pages,
		"uom": item.uom,
		"rate": flt(item.rate),
	}
	current = {key: category.get(key) for key in incoming}
	if all(same(current[key], value) for key, value in incoming.items()):
		return False
	follow_first_line(view, category, incoming)
	category.update(incoming)
	return True


def follow_first_line(view, category, incoming):
	lines = view.siblings(category.row_key)
	first = lines[0] if lines else None
	if not first or first.row_type == CATEGORY:
		return
	for key in ("qty", "days", "uom", "description"):
		if same(first.get(key), category.get(key)):
			first.set(key, incoming[key])
	if same(first.unit_cost, category.rate):  # an estimate still equal to the old price moves with it
		first.unit_cost = incoming["rate"]


def same(a, b):
	if isinstance(a, (int, float)) or isinstance(b, (int, float)):
		return abs(flt(a) - flt(b)) < 0.0005
	return (a or "") == (b or "")
