"""Planner grid columns: an admin list in Settings (what can appear) and each user's choice (what they see)."""

import json

import frappe
from frappe import _
from frappe.utils import flt

SETTINGS = "Commercial Planning Settings"
USER_KEY = "commercial_planning_columns"
ITEM_DOCTYPE = {"Quotation": "Quotation Item", "Sales Order": "Sales Order Item"}

# key: (label, width, applies to, shown by default). "cost" stands for one column per version on screen.
BUILTIN = {
	"description": ("Description", 380, "Both", 1),
	"basis": ("Cost from", 140, "Cost lines", 1),
	"qty": ("Qty", 72, "Both", 1),
	"days": ("Days", 68, "Both", 1),
	"pages": ("Pages", 68, "Client lines", 0),
	"uom": ("UOM", 84, "Both", 0),
	"rate": ("Rate", 112, "Client lines", 1),
	"unit_cost": ("Unit cost", 112, "Both", 1),
	"cost": ("Total cost", 124, "Both", 1),
	"delta": ("vs reference", 112, "Both", 1),
	"supplier": ("Supplier", 150, "Cost lines", 0),
	"ordered": ("Ordered", 110, "Both", 0),  # shown by the After win view; zeros before winning are noise
	"spent": ("Spent", 110, "Both", 0),
	"left": ("Left", 110, "Both", 0),
	"selling": ("Selling", 124, "Both", 1),
	"profit": ("Profit", 116, "Both", 1),
	"margin": ("Margin", 84, "Both", 1),
}


def available():
	"""Columns users may show, in the admin's order. Description is always there."""
	rows = frappe.get_cached_doc(SETTINGS).get("planner_columns") or []
	if not rows:
		return [column(key, *spec) for key, spec in BUILTIN.items()]
	found = []
	for row in rows:
		spec = BUILTIN.get(row.column_key)
		label, width, applies, _shown = spec or (row.column_key.replace("_", " ").title(), 120, "Client lines", 1)
		found.append(
			column(row.column_key, row.label or label, row.width or width, row.applies_to or applies, row.shown_by_default,
				editable=bool(row.editable), item_field=spec is None)
		)
	if not any(col["key"] == "description" for col in found):
		found.insert(0, column("description", *BUILTIN["description"]))
	return found


def column(key, label, width, applies_to, shown, editable=False, item_field=False):
	return {"key": key, "label": _(label), "width": width, "applies_to": applies_to, "shown": bool(shown),
		"editable": editable, "item_field": item_field}


def item_fields():
	return [col for col in available() if col["item_field"]]


def chosen():
	"""The user's saved choice: [{key, width}] in their order, or None (use the defaults)."""
	raw = frappe.defaults.get_user_default(USER_KEY)
	try:
		return json.loads(raw) if raw else None
	except ValueError:
		return None


def save_choice(choice):
	keys = {col["key"] for col in available()}
	clean = [{"key": c["key"], "width": int(c["width"])} if c.get("width") else {"key": c["key"]} for c in choice if c.get("key") in keys]
	frappe.defaults.set_user_default(USER_KEY, json.dumps(clean))
	return clean


def item_values(version, fields):
	"""{row_key: {field: value}} from the document items linked to client lines, for Quotation Item columns."""
	doctype = ITEM_DOCTYPE.get(version.source_doctype)
	if not doctype or not fields:
		return {}
	meta = frappe.get_meta(doctype)
	names = [f for f in fields if meta.has_field(f)]
	links = [link for link in version.item_links if link.link_doctype == doctype]
	if not names or not links:
		return {}
	items = {
		row.name: row
		for row in frappe.get_all(doctype, filters={"name": ["in", [link.link_name for link in links]]}, fields=["name", *names])
	}
	return {link.row_key: {f: items[link.link_name].get(f) for f in names} for link in links if link.link_name in items}


def set_item_field(version, row_key, field, value):
	"""The planner no longer writes Quotation items: client lines are changed in the Quotation, then synced."""
	from commercial_planning.services import quote_sync

	if quote_sync.active_quotation(version):
		frappe.throw(_("Quotation items are changed in the Quotation, then synced here"))
	spec = next((col for col in item_fields() if col["key"] == field), None)
	if not spec or not spec["editable"]:
		frappe.throw(_("{0} is not an editable planner column").format(field))
	quotation = quote_sync.active_quotation(version)
	if not quotation:
		frappe.throw(_("The Quotation is not an editable draft, so its items cannot be changed from the plan"))
	row = next((r for r in version.items if r.row_key == row_key), None)
	link = row and quote_sync.single_link(version, row)
	item = link and next((i for i in quotation.items if i.name == link.link_name), None)
	if not item:
		frappe.throw(_("This line has no single Quotation item to update"))
	item.set(field, value)
	if field == "discount_percentage" and flt(item.price_list_rate):
		item.rate = flt(item.price_list_rate) * (1 - flt(value) / 100)  # on the server ERPNext derives the discount from rate
	quotation.flags.from_planner = True
	quotation.save()
	saved = next(i for i in quotation.items if i.name == item.name)
	if not quote_sync.same(row.rate, saved.rate):  # the price moved: the client line follows
		row.rate = saved.rate
		from commercial_planning.services import selling

		selling.refresh_selling(version)
		version.save()
