"""Internal BOQ pricing: what sales can build the client price from.

Only the lines marked important (and every sourced line) count toward the price. Small items are
covered by an allowance on the important cost. The client never sees these figures.
"""

import frappe
from frappe import _
from frappe.utils import flt

SOURCED = ("Sub-hire", "Outsourced")
SMALL = "Small item"


def is_important(line):
	return bool(line.important) or line.line_kind in SOURCED


def price_breakdown(lines, allowance_pct, margin_pct):
	"""Important cost, the small-items allowance on it, and the price it suggests with the margin target."""
	important = sum(flt(line.cost_amount) for line in lines if line.line_kind != SMALL and is_important(line))
	allowance = important * flt(allowance_pct) / 100
	suggested = (important + allowance) * (1 + flt(margin_pct) / 100)
	return {"important_cost": important, "allowance_amount": allowance, "suggested_selling": suggested}


def override_problem(selling, suggested, tolerance_pct, reason):
	"""Why the client price needs a reason (None when it does not)."""
	if not suggested or (reason or "").strip():
		return None
	gap = abs(flt(selling) - suggested) / suggested * 100
	if gap > flt(tolerance_pct):
		return _("the client price is {0:.1f}% away from the suggested price; give a reason").format(gap)
	return None


def refresh_pricing(revision, view):
	"""Fill each client line's BOQ figures from its cost lines (called from the tree recalculation)."""
	from commercial_planning.services.tree import CATEGORY, COST_ITEM

	settings = frappe.get_cached_doc("Commercial Planning Settings")
	for row in revision.items:
		if row.row_type != CATEGORY:
			continue
		lines = [line for line in view.siblings(row.row_key) if line.row_type == COST_ITEM]
		pct = settings.default_allowance_pct if row.allowance_pct is None else row.allowance_pct
		figures = price_breakdown(lines, pct, settings.margin_target_pct)
		row.important_cost = figures["important_cost"]
		row.allowance_amount = figures["allowance_amount"]
		row.suggested_selling = figures["suggested_selling"]


def check_overrides(revision):
	"""Refuse a client price that is off the suggestion by more than the tolerance without a reason."""
	from commercial_planning.services.tree import CATEGORY

	settings = frappe.get_cached_doc("Commercial Planning Settings")
	for row in revision.items:
		if row.row_type != CATEGORY or not flt(row.important_cost):
			continue
		problem = override_problem(row.selling_amount, row.suggested_selling, settings.price_tolerance_pct, row.price_override_reason)
		if problem:
			frappe.throw(_("{0}: {1}").format(row.description, problem), frappe.ValidationError)
