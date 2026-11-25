"""What the rental app books for a version: its inventory lines, the small-items request, and what is left out.

Sourced lines (sub-hire, outsourced) are not stock, so they stay with sourcing. Lines without a rental
item are reported, so the warehouse never gets a silently shorter list.
"""

from frappe.utils import flt

from commercial_planning.services.pricing import SMALL, SOURCED


def build_request(lines, category_titles):
	"""lines: cost lines (line_kind, rental_item, qty, days, uom, parent_key, description, variance_qty)."""
	booking, small, unmapped = [], [], []
	for line in lines:
		if line.line_kind in SOURCED:
			continue
		entry = {
			"category": category_titles.get(line.parent_key, ""),
			"description": line.description,
			"qty": flt(line.qty) + flt(line.variance_qty),
			"days": flt(line.days) or 1,
			"uom": line.uom,
		}
		if line.line_kind == SMALL:
			small.append(entry)
		elif line.rental_item:
			booking.append({**entry, "item": line.rental_item})
		else:
			unmapped.append(line.description)
	return {"booking": booking, "small_items": small, "unmapped": unmapped}


def for_version(revision):
	from commercial_planning.services.tree import CATEGORY, COST_ITEM

	titles = {row.row_key: row.description for row in revision.items if row.row_type == CATEGORY}
	lines = [row for row in revision.items if row.row_type == COST_ITEM]
	return build_request(lines, titles)
