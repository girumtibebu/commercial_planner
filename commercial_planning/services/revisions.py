"""After winning (v2, phase 3): budget revisions with an approval rule, free extras and billed variations.

Once the Sales Order is submitted its version is the Agreed budget. A new version made after that is a
revision. Submitting a revision checks the rule against the latest Estimate: nothing triggers -> approved at
once and it becomes the Estimate; something triggers -> it waits, locked, for the approver role.
Client lines added in a revision sit "after agreement": price 0 is a free extra; Bill to client turns them
into a draft Variation Sales Order, which adds to Agreed budget and price once submitted."""

import json

import frappe
from frappe import _
from frappe.utils import add_days, flt, nowdate

from commercial_planning.services import lifecycle

VERSION = "Commercial Planning Version"
PLAN = "Commercial Planning"
SETTINGS = "Commercial Planning Settings"
CATEGORY = "Category"


# ------------------------------------------------------------------ what counts as agreed
def agreed_version(planning):
	name = frappe.db.get_value(VERSION, {"planning": planning, "lock_kind": "Agreed"}, "name", order_by="version_no desc")
	return frappe.get_doc(VERSION, name) if name else None


def is_won(planning):
	return bool(frappe.db.exists(VERSION, {"planning": planning, "lock_kind": "Agreed"}))


def estimate_version(planning):
	"""The latest approved revision, else the Agreed budget."""
	name = frappe.db.get_value(
		VERSION, {"planning": planning, "is_revision": 1, "revision_status": "Approved"}, "name", order_by="version_no desc"
	)
	return frappe.get_doc(VERSION, name) if name else agreed_version(planning)


def is_variation(sales_order):
	"""A Sales Order the planner raised for lines added after agreement."""
	return bool(frappe.db.exists("Commercial Planning Item", {"variation_order": sales_order}))


def variations(planning):
	"""{sales_order: {status, docstatus, net_total}} for the plan's variation orders."""
	names = frappe.db.sql(
		f"""select distinct item.variation_order from `tabCommercial Planning Item` item
		join `tab{VERSION}` ver on ver.name = item.parent where ver.planning = %s and ifnull(item.variation_order, '') != ''""",
		planning,
	)
	found = {}
	for (name,) in names:
		row = frappe.db.get_value("Sales Order", name, ["status", "docstatus", "net_total", "workflow_state"], as_dict=True)
		if row:
			found[name] = row
	return found


def agreed_totals(planning):
	"""Agreed cost and price: the original agreement plus submitted variations (their cost in the Estimate)."""
	agreed = agreed_version(planning)
	if not agreed:
		return None
	cost, price = flt(agreed.total_cost), flt(agreed.total_selling)
	submitted = {name for name, row in variations(planning).items() if row.docstatus == 1}
	if submitted:
		estimate = estimate_version(planning)
		cost += sum(flt(row.cost_amount) for row in estimate.items if row.variation_order in submitted and row.row_type == CATEGORY)
		price += sum(flt(row.net_total) for name, row in variations(planning).items() if name in submitted)
	return {"cost": cost, "price": price}


# ------------------------------------------------------------------ the approval rule
def rule():
	conf = frappe.get_cached_doc(SETTINGS)
	return {
		"line_threshold": flt(conf.get("line_threshold")),
		"line_change_pct": flt(conf.get("line_change_pct")),
		"job_change_pct": flt(conf.get("job_change_pct")),
	}


def reasons_for(revision):
	"""Why a revision needs approval (empty: it does not). Client lines are compared with the latest Estimate
	(the last approved revision, else the Agreed budget), so a change approved once is not asked for again."""
	agreed = estimate_version(revision.planning)
	limits = rule()
	found = []
	before = {row.row_key: row for row in agreed.items if row.row_type == CATEGORY and not row.parent_key}
	for row in revision.items:
		if row.row_type != CATEGORY or row.parent_key:
			continue
		cost = flt(row.cost_amount)
		old = before.get(row.row_key)
		if old is None:
			if limits["line_threshold"] and cost >= limits["line_threshold"] and not row.variation_order:
				found.append(_("Free extra {0}: cost {1} is at or above the line threshold {2}").format(
					row.description, frappe.format(cost, "Currency"), frappe.format(limits["line_threshold"], "Currency")))
			continue
		was = flt(old.cost_amount)
		if limits["line_threshold"] and was >= limits["line_threshold"] and was:
			change = abs(cost - was) / was * 100
			if change >= limits["line_change_pct"]:
				found.append(_("{0}: {1} → {2} ({3}%, limit {4}%)").format(
					row.description, frappe.format(was, "Currency"), frappe.format(cost, "Currency"), round(change, 1), limits["line_change_pct"]))
	total, was_total = flt(revision.total_cost), flt(agreed.total_cost)
	if limits["job_change_pct"] and was_total:
		change = abs(total - was_total) / was_total * 100
		if change >= limits["job_change_pct"]:
			found.append(_("Job total: {0} → {1} ({2}%, limit {3}%)").format(
				frappe.format(was_total, "Currency"), frappe.format(total, "Currency"), round(change, 1), limits["job_change_pct"]))
	return found


# ------------------------------------------------------------------ revision flow
def require_revision(version, status):
	if not version.is_revision:
		frappe.throw(_("{0} is not a budget revision").format(version.name))
	if (version.revision_status or "Draft") != status:
		frappe.throw(_("{0} is {1}").format(version.name, version.revision_status or _("a draft")))


def submit(version):
	"""Check the rule: approve at once, or lock and wait for the approver."""
	require_revision(version, "Draft")
	if version.status != "Working":
		frappe.throw(_("{0} is locked").format(version.name))
	waiting = frappe.db.get_value(VERSION, {"planning": version.planning, "revision_status": "Needs approval"}, "name")
	if waiting:
		frappe.throw(_("{0} is already waiting for approval; approve or reject it first").format(waiting))
	reasons = reasons_for(version)
	if not reasons:
		return mark_approved(version, _("Approved automatically: within the approval rule"))
	lifecycle.lock(version, "Approval", _("Waiting for approval"), revision_status="Needs approval",
		approval_reasons=json.dumps(reasons), reject_reason=None)
	notify(version, reasons)
	return version


def approve(version):
	require_revision(version, "Needs approval")
	if not can_approve():
		frappe.throw(_("Only {0} can approve budget revisions").format(approver_role()), frappe.PermissionError)
	return mark_approved(version, _("Approved by {0}").format(frappe.session.user))


def mark_approved(version, note):
	version.approved_by, version.approved_on = frappe.session.user, frappe.utils.now_datetime()
	lifecycle.lock(version, "Revision", _("Approved revision · Estimate"), revision_status="Approved")
	version.add_comment("Info", note)
	return version


def reject(version, reason):
	require_revision(version, "Needs approval")
	if not can_approve():
		frappe.throw(_("Only {0} can reject budget revisions").format(approver_role()), frappe.PermissionError)
	if not (reason or "").strip():
		frappe.throw(_("Give a reason for rejecting"))
	version.revision_status, version.reject_reason = "Draft", reason.strip()
	lifecycle.unlock(version, _("Revision rejected: {0}").format(reason.strip()))
	return version


def approver_role():
	return frappe.get_cached_doc(SETTINGS).get("approver_role") or "Management"


def can_approve(user=None):
	roles = frappe.get_roles(user)
	return approver_role() in roles or "System Manager" in roles


def notify(version, reasons):
	from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

	users = frappe.get_all("Has Role", {"role": approver_role(), "parenttype": "User"}, pluck="parent", distinct=True)
	users = [u for u in users if u not in ("Administrator", "Guest") and frappe.db.get_value("User", u, "enabled")]
	if users:
		enqueue_create_notification(users, {
			"type": "Alert",
			"document_type": VERSION,
			"document_name": version.name,
			"subject": _("Budget revision {0} needs your approval").format(version.name),
			"email_content": "<br>".join(frappe.utils.escape_html(r) for r in reasons),
		})


# ------------------------------------------------------------------ variations
def bill_to_client(version, row_keys):
	"""A draft Variation Sales Order for client lines added after agreement; it goes through the normal approval."""
	plan = frappe.get_doc(PLAN, version.planning)
	if not plan.sales_order:
		frappe.throw(_("The plan has no Sales Order to vary"))
	original = frappe.get_doc("Sales Order", plan.sales_order)
	rows = [row for row in version.items if row.row_key in set(row_keys or [])]
	if not rows:
		frappe.throw(_("Pick the lines to bill"))
	for row in rows:
		if row.row_type != CATEGORY or row.parent_key or not row.after_agreement:
			frappe.throw(_("Only client lines added after agreement can be billed ({0})").format(row.description))
		if row.variation_order:
			frappe.throw(_("{0} is already on {1}").format(row.description, row.variation_order))
		if flt(row.rate) <= 0:
			frappe.throw(_("Set a rate on {0} before billing it").format(row.description))
	from commercial_planning.services.quote_sync import units_to_item

	conf = frappe.get_cached_doc(SETTINGS)
	order = frappe.get_doc({
		"doctype": "Sales Order",
		"company": original.company,
		"customer": original.customer,
		"currency": original.currency,
		"selling_price_list": original.selling_price_list,
		"transaction_date": nowdate(),
		"delivery_date": max(str(original.delivery_date or nowdate()), nowdate()) if original.delivery_date else add_days(nowdate(), 7),
		"project": plan.project,
		"items": [{
			"item_code": row.item_code or conf.default_service_item,
			"item_name": row.description,
			"description": _("{0} (variation of {1})").format(row.description, original.name),
			"rate": flt(row.rate),
			"price_list_rate": flt(row.rate),
			"uom": row.uom or None,
			"conversion_factor": 1,
			"project": plan.project,
			**units_to_item(row, "Sales Order Item"),
		} for row in rows],
	})
	order.flags.cp_variation = True
	order.insert()
	# the row_key is shared by every copy of the line, so all versions know which order bills it
	frappe.db.sql(
		f"""update `tabCommercial Planning Item` item join `tab{VERSION}` ver on ver.name = item.parent
		set item.variation_order = %s where ver.planning = %s and item.row_key in %s""",
		(order.name, plan.name, tuple(row.row_key for row in rows)),
	)
	frappe.get_doc(PLAN, plan.name).add_comment("Info", _("Variation Sales Order {0} drafted for {1}").format(
		order.name, ", ".join(row.description for row in rows)))
	return order.name
