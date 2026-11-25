"""Cost tree of a revision: structure rules, row operations and rollups."""

import frappe
from frappe import _
from frappe.utils import flt

MAX_DEPTH = 6
CATEGORY, COST_ITEM, ADJUSTMENT = "Category", "Cost Item", "Adjustment"

EDITABLE_FIELDS = (
	"description",
	"notes",
	"row_type",
	"cost_type",
	"cost_source",
	"item_code",
	"supplier",
	"vendor_quote",
	"qty",
	"days",
	"pages",
	"rate",
	"uom",
	"unit_cost",
	"cost_currency",
	"exchange_rate",
	"adj_mode",
	"adj_percent",
	"pricing_basis",
)
# a client line's own fields: they are the Quotation item, so they change only where the Quotation allows it
CLIENT_FIELDS = ("description", "item_code", "qty", "days", "pages", "rate")




def new_row_key():
	return frappe.generate_hash(length=8)


def default_line_values(category):
	"""First line of a category: same name, quoted qty/uom, no cost yet."""
	return {
		"row_type": COST_ITEM,
		"row_key": new_row_key(),
		"description": category.description,
		"item_code": category.item_code,  # the first line is the quoted item itself: RFQs and POs need a real item
		"qty": category.qty or 1,
		"days": category.days or 1,
		"uom": category.uom,
		"pricing_basis": "Manual",
	}


class Tree:
	"""Ordered parent/child view over `revision.items`; `flush` writes the order back."""

	def __init__(self, revision):
		self.revision = revision
		self._sync = None
		self.children = {}
		self.rows = {}
		for row in revision.items:
			self.rows[row.row_key] = row
			self.children.setdefault(row.parent_key or "", []).append(row)

	def client_editable(self, row):
		"""Client fields of a linked client line are editable only while its draft Quotation syncs."""
		if not any(link.row_key == row.row_key for link in self.revision.item_links):
			return True
		if self._sync is None:
			from commercial_planning.services import quote_sync

			self._sync = bool(quote_sync.active_quotation(self.revision))
		return self._sync

	def get(self, row_key):
		row = self.rows.get(row_key)
		if not row:
			frappe.throw(_("Row {0} does not exist in this revision").format(row_key))
		return row

	def siblings(self, parent_key):
		return self.children.setdefault(parent_key or "", [])

	def depth(self, row_key):
		depth = 0
		while row_key:
			depth += 1
			row_key = self.rows[row_key].parent_key
		return depth

	def subtree(self, row):
		found = [row]
		for child in self.siblings(row.row_key):
			found.extend(self.subtree(child))
		return found

	def height(self, row):
		kids = self.siblings(row.row_key)
		return 1 + max((self.height(kid) for kid in kids), default=0)

	def ordered(self, parent_key=""):
		for row in self.siblings(parent_key):
			yield row
			yield from self.ordered(row.row_key)

	def flush(self):
		ordered = list(self.ordered())
		for index, row in enumerate(ordered, start=1):
			row.idx = index
		self.revision.items = ordered

	def attach(self, row, parent_key, before_key=None):
		self.check_parent(row, parent_key)
		siblings = self.siblings(parent_key)
		row.parent_key = parent_key or ""
		position = len(siblings)
		if before_key:
			position = next((i for i, s in enumerate(siblings) if s.row_key == before_key), position)
		siblings.insert(position, row)
		self.rows[row.row_key] = row

	def detach(self, row):
		self.siblings(row.parent_key).remove(row)

	def check_parent(self, row, parent_key):
		"""Two levels only: a category (a quotation line) sits at the top; cost lines sit inside a category."""
		if row.row_type == CATEGORY:
			if parent_key:
				frappe.throw(_("Categories stay at the top level; only lines go inside a category"))
			return
		if not parent_key:
			frappe.throw(_("A line belongs inside a category"))
		parent = self.get(parent_key)
		if parent.row_type != CATEGORY or parent.parent_key:
			frappe.throw(_("Lines can only be placed inside a category"))


def apply_ops(revision, ops):
	"""Apply a list of row operations in order; returns {temp_id: row_key} for added rows."""
	tree = Tree(revision)
	created = {}
	for op in ops:
		handler = OPERATIONS.get(op.get("op"))
		if not handler:
			frappe.throw(_("Unknown operation {0}").format(op.get("op")))
		handler(revision, tree, op, created)
	# what the client signed comes first; lines added after agreement stay below the divider
	tree.children[""] = sorted(tree.siblings(""), key=lambda row: bool(row.after_agreement))
	tree.flush()
	fill_lta(revision)
	recalculate(revision)
	from commercial_planning.services import selling

	selling.refresh_selling(revision)
	return created


CATEGORY_CALCULATED = ("uom", "unit_cost")


def clean_values(values):
	return {key: value for key, value in (values or {}).items() if key in EDITABLE_FIELDS}


def reject_calculated(row, values):
	"""A category's UOM and unit cost come from the document item and its lines; they are not typed."""
	if row.row_type == CATEGORY and any(key in values for key in CATEGORY_CALCULATED):
		frappe.throw(_("UOM and unit cost of a client line are calculated; edit its cost lines instead"))


def op_add(revision, tree, op, created):
	values = clean_values(op.get("values"))
	if values.get("row_type") == CATEGORY:
		values = {key: value for key, value in values.items() if key not in CATEGORY_CALCULATED}
	days = event_days(revision)
	if values.get("row_type") == CATEGORY and revision.is_revision:
		# added after the Sales Order: below the "Added after agreement" divider, free until billed
		values.update(after_agreement=1, rate=flt(values.get("rate")))
		op = {**op, "parent_key": "", "before_key": None}
	row = revision.append("items", {"row_type": COST_ITEM, "qty": 1, "days": days, **values})
	row.row_key = new_row_key()
	tree.rows[row.row_key] = row
	tree.attach(row, op.get("parent_key"), op.get("before_key"))
	normalise_row(row)
	if row.row_type == CATEGORY:
		add_default_line(revision, tree, row)
	if op.get("temp_id"):
		created[op["temp_id"]] = row.row_key


def add_default_line(revision, tree, category):
	if tree.depth(category.row_key) >= MAX_DEPTH:
		return None
	line = revision.append("items", default_line_values(category))
	tree.rows[line.row_key] = line
	tree.attach(line, category.row_key)
	return line


def op_update(revision, tree, op, created):
	row = tree.get(op["row_key"])
	values = clean_values(op.get("values"))
	new_type = values.get("row_type")
	if new_type and new_type != row.row_type:
		change_type(revision, tree, row, new_type)
	if row.row_type == CATEGORY:
		reject_calculated(row, values)
		if any(key in values for key in CLIENT_FIELDS) and row.variation_order:
			frappe.throw(_("{0} is billed on {1}: change it there").format(row.description, row.variation_order))
		if any(key in values for key in CLIENT_FIELDS) and not tree.client_editable(row):
			frappe.throw(_("{0} follows {1} {2}, which can no longer be edited. Make the change there, or in a new version").format(
				row.description, revision.source_doctype, revision.source_name))
		row.changed_in_quotation = 0
	reject_typed_quote_cost(row, values)
	previous_name = row.description
	row.update(values)
	normalise_row(row)
	if row.row_type == CATEGORY and "description" in values:
		rename_first_line(tree, row, previous_name)


def reject_typed_quote_cost(row, values):
	"""A Requirement line is priced only by the quote picked in Sourcing, an LTA line by the LTA price list;
	typing a cost would bypass them."""
	basis = values.get("pricing_basis", row.pricing_basis)
	if basis == "Requirement" and flt(values.get("unit_cost")):
		frappe.throw(_("{0} is priced from its RFQ. Select a supplier quote in Sourcing, or change Cost From to Manual").format(row.description))
	if basis == "LTA" and flt(values.get("unit_cost")):
		frappe.throw(_("{0} takes its cost from the LTA price list. Change Cost From to Manual to type a cost").format(row.description))


def fill_lta(revision):
	"""LTA lines take their unit cost from the LTA price list (supplier-specific price first); 0 when it has none."""
	lines = [row for row in revision.items if row.row_type == COST_ITEM and row.pricing_basis == "LTA"]
	price_list = lines and frappe.get_cached_doc("Commercial Planning Settings").get("lta_price_list")
	if not price_list:
		return
	from commercial_planning.services.sourcing import lta_rate

	for row in lines:
		rate = lta_rate(price_list, row.item_code, row.supplier)
		row.unit_cost, row.exchange_rate = flt(rate), 1
		row.cost_source = "LTA Price" if rate is not None else None


def rename_first_line(tree, category, previous_name):
	"""A first line still carrying the category's old name follows the rename."""
	lines = tree.siblings(category.row_key)
	first = lines[0] if lines else None
	if first and first.row_type == COST_ITEM and (first.description or "") == (previous_name or ""):
		first.description = category.description


def event_days(revision):
	"""Plan-level default days for new lines, else the Settings default (1 when unset)."""
	return (
		flt(frappe.db.get_value("Commercial Planning", revision.planning, "event_days"))
		or flt(frappe.db.get_single_value("Commercial Planning Settings", "default_event_days"))
		or 1
	)


def change_type(revision, tree, row, new_type):
	# Two levels only: a line cannot become a category (that would nest one) and a category cannot become a line.
	if CATEGORY in (row.row_type, new_type):
		frappe.throw(_("A category and a line cannot be turned into each other; add a category or a line instead"))


def op_delete(revision, tree, op, created):
	row = tree.get(op["row_key"])
	doomed = {r.row_key for r in tree.subtree(row)}
	tree.detach(row)
	revision.items = [r for r in revision.items if r.row_key not in doomed]
	revision.item_links = [link for link in revision.item_links if link.row_key not in doomed]
	for key in doomed:
		tree.rows.pop(key, None)
		tree.children.pop(key, None)


def op_move(revision, tree, op, created):
	row = tree.get(op["row_key"])
	tree.check_parent(row, op.get("parent_key"))
	target = tree.rows.get(op.get("before_key") or "")
	if row.row_type == CATEGORY and target is not None and bool(target.after_agreement) != bool(row.after_agreement):
		frappe.throw(_("Lines added after agreement stay below the divider"))
	tree.detach(row)
	tree.attach(row, op.get("parent_key"), op.get("before_key"))


def op_indent(revision, tree, op, created):
	row = tree.get(op["row_key"])
	siblings = tree.siblings(row.parent_key)
	index = siblings.index(row)
	if index == 0:
		frappe.throw(_("There is no row above to indent under"))
	new_parent = siblings[index - 1]
	if new_parent.row_type != CATEGORY:
		frappe.throw(_("Rows can only be indented under a Category; split the row above first"))
	tree.detach(row)
	tree.attach(row, new_parent.row_key)


def op_outdent(revision, tree, op, created):
	row = tree.get(op["row_key"])
	if not row.parent_key:
		return
	parent = tree.get(row.parent_key)
	siblings = tree.siblings(parent.parent_key)
	after = siblings[siblings.index(parent) + 1].row_key if siblings.index(parent) + 1 < len(siblings) else None
	tree.detach(row)
	tree.attach(row, parent.parent_key, after)


def op_duplicate(revision, tree, op, created):
	source = tree.get(op["row_key"])
	copies = {}
	for original in tree.subtree(source):
		data = {key: original.get(key) for key in EDITABLE_FIELDS + ("row_type",)}
		copy = revision.append("items", data)
		copy.row_key = new_row_key()
		copies[original.row_key] = copy
		tree.rows[copy.row_key] = copy
	for original_key, copy in copies.items():
		original = tree.rows[original_key]
		if original is source:
			siblings = tree.siblings(source.parent_key)
			after = siblings[siblings.index(source) + 1].row_key if siblings.index(source) + 1 < len(siblings) else None
			tree.attach(copy, source.parent_key, after)
		else:
			tree.attach(copy, copies[original.parent_key].row_key)


def op_split(revision, tree, op, created):
	"""Splitting a line made it a sub-category; the plan keeps two levels, so add lines to the category instead."""
	frappe.throw(_("Lines cannot be split. Add another line to the category instead"))


def op_sync_source(revision, tree, op, created):
	from commercial_planning.services import sync

	sync.add_missing_items(revision, tree, set(op.get("items") or []))


def op_refresh_source(revision, tree, op, created):
	from commercial_planning.services import sync

	sync.refresh_rows(revision, tree, set(op.get("rows") or []))


def op_set_links(revision, tree, op, created):
	row = tree.get(op["row_key"])
	if row.parent_key or row.row_type != CATEGORY:
		frappe.throw(_("Document items can only be linked to top-level Categories"))
	revision.item_links = [link for link in revision.item_links if link.row_key != row.row_key]
	for link in op.get("links") or []:
		revision.append(
			"item_links",
			{
				"row_key": row.row_key,
				"link_doctype": link["link_doctype"],
				"link_name": link["link_name"],
				"allocation_pct": flt(link.get("allocation_pct", 100)),
			},
		)
	from commercial_planning.services import selling

	selling.refresh_selling(revision, {row.row_key})


OPERATIONS = {
	"add": op_add,
	"update": op_update,
	"delete": op_delete,
	"move": op_move,
	"indent": op_indent,
	"outdent": op_outdent,
	"duplicate": op_duplicate,
	"split": op_split,
	"set_links": op_set_links,
	"sync_source": op_sync_source,
	"refresh_source": op_refresh_source,
}


def normalise_row(row):
	if row.row_type == COST_ITEM and not row.pricing_basis:
		row.pricing_basis = "Manual"
	if row.row_type != ADJUSTMENT:
		row.adj_mode = None
		row.adj_percent = 0
	elif not row.adj_mode:
		row.adj_mode = "Percent of parent"
	if not row.exchange_rate:
		row.exchange_rate = 1


def recalculate(revision):
	"""Recompute every row's cost_amount bottom-up and the revision totals."""
	view = Tree(revision)
	total = group_cost(view, "")
	derive_category_fields(revision, view)
	revision.total_cost = total
	return total


def derive_category_fields(revision, view):
	"""A client line's UOM follows its first line when no document item sets it; unit cost = cost per
	unit per day (comparable with its rate)."""
	linked = {link.row_key for link in revision.item_links}
	for row in revision.items:
		if row.row_type != CATEGORY:
			continue
		first = next(iter(view.siblings(row.row_key)), None)
		if row.row_key not in linked and first and first.row_type == COST_ITEM and not row.uom:
			row.uom = first.uom
		units = flt(row.qty) * (flt(row.days) or 1) * (flt(row.pages) or 1)
		row.unit_cost = flt(row.cost_amount) / units if units else 0


def leaf_cost(row):
	return flt(row.qty) * (flt(row.days) or 1) * flt(row.unit_cost) * (flt(row.exchange_rate) or 1)


def group_cost(tree, parent_key):
	"""Cost of one sibling group: leaves + nested categories, then adjustments on that base."""
	base = 0.0
	adjustments = []
	for row in tree.siblings(parent_key):
		if row.row_type == ADJUSTMENT:
			adjustments.append(row)
			continue
		if row.row_type == CATEGORY:
			row.cost_amount = group_cost(tree, row.row_key)
		else:
			row.cost_amount = leaf_cost(row)
		base += flt(row.cost_amount)
	total = base
	for row in adjustments:
		if row.adj_mode == "Fixed":
			row.cost_amount = leaf_cost(row)
		else:
			row.cost_amount = base * flt(row.adj_percent) / 100
		total += flt(row.cost_amount)
	return total
