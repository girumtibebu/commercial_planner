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


# ------------------------------------------------------------------ planner -> Quotation
COMPARED = ("item_code", "item_name", "qty", "rate", "uom") + UNIT_FIELDS


def push(version):
	"""Write the client lines to the draft Quotation (add, update, remove, reorder). Returns True if it saved."""
	quotation = active_quotation(version)
	if not quotation:
		return False
	conf = frappe.get_cached_doc("Commercial Planning Settings")
	by_name = {item.name: item for item in quotation.items}
	ordered, created = [], []
	for row in client_lines(version):
		if row.off_quotation:
			continue
		link = single_link(version, row)
		if link and link.link_name in by_name:
			item = by_name[link.link_name]
			values = item_values(row, item.item_code)
			if same(item.rate, row.rate):  # price unchanged: keep the item's own discount and price list rate
				for key in PRICE_FIELDS:
					values.pop(key)
			ordered.append({**item.as_dict(), **values})
		elif not any(l.row_key == row.row_key for l in version.item_links):
			ordered.append(new_item(row, conf, quotation.company))
			created.append(row)
	placed = {item.get("name") for item in ordered}
	keepers = [item for item in quotation.items if item.name not in placed and (not is_line_item(item) or linked_elsewhere(version, item))]
	final = place_keepers(quotation.items, keepers, ordered)
	if signature(quotation.items) == signature(final):
		return False
	old_names = set(by_name)
	quotation.items = []
	for item in final:
		data = dict(item if isinstance(item, dict) else item.as_dict())
		data.pop("idx", None)  # a kept idx would restore the old order on save
		quotation.append("items", data)
	quotation.flags.from_planner = True
	quotation.save()
	fresh = [item for item in quotation.items if item.name not in old_names]
	for row, item in zip(created, fresh):
		version.append("item_links", {"row_key": row.row_key, "link_doctype": ITEM, "link_name": item.name, "allocation_pct": 100})
		row.item_code = row.item_code or item.item_code
	selling.refresh_selling(version)
	return True


def signature(items):
	return [(item.get("name"),) + tuple(round(flt(v), 4) if isinstance(v, (int, float)) else (v or "") for v in (item.get(f) for f in COMPARED)) for item in items]


def linked_elsewhere(version, item):
	"""An item a split client line still points at stays on the Quotation."""
	return any(link.link_name == item.name for link in version.item_links)


def place_keepers(original, keepers, ordered):
	"""Client items in plan order; each section or alternative row stays just before the item it preceded."""
	result = list(ordered)
	names = [item.name for item in original]
	placed = {item.get("name") for item in ordered}
	for keeper in keepers:
		following = [name for name in names[names.index(keeper.name) + 1 :] if name in placed]
		index = next((i for i, item in enumerate(result) if item.get("name") == following[0]), len(result)) if following else len(result)
		result.insert(index, keeper)
	return result


PRICE_FIELDS = ("rate", "price_list_rate", "discount_percentage", "discount_amount", "margin_rate_or_amount")


def item_values(row, item_code):
	return {
		"item_code": row.item_code or item_code,
		"item_name": row.description,
		"description": row.description,
		"rate": flt(row.rate),
		"price_list_rate": flt(row.rate),
		"discount_percentage": 0,
		"discount_amount": 0,
		"margin_rate_or_amount": 0,
		**units_to_item(row, ITEM),
	}


def new_item(row, conf, company):
	code = row.item_code or conf.default_service_item
	if not code:
		frappe.throw(_("{0} has no item. Pick one, or set a Default Service Item in Commercial Planning Settings").format(row.description))
	item = {
		**item_values(row, code),
		"item_code": code,
		"uom": row.uom or frappe.get_cached_value("Item", code, "stock_uom"),
		"conversion_factor": 1,
	}
	if conf.lead_cost_center and frappe.get_cached_value("Cost Center", conf.lead_cost_center, "company") == company:
		item["cost_center"] = conf.lead_cost_center  # the lead division books the sale; other companies keep their default
	return item


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
