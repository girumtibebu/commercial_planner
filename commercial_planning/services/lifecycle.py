"""The plan follows the Quotation / Sales Order workflow (v2, phase 1).

A version is built on one document (its source). While that document is in a draft workflow state the
version is editable; once it leaves draft (pending, approved) the version locks for review; back to draft
unlocks it. Submit keeps it locked for good: a Quotation's becomes "Round N" (what the client was offered),
a Sales Order's becomes the "Agreed budget" and the job's Project is created. Nothing here blocks the
document: callers run it guarded."""

import frappe
from frappe import _
from frappe.utils import now_datetime

VERSION = "Commercial Planning Version"
PLAN = "Commercial Planning"
SETTINGS = "Commercial Planning Settings"
DEFAULT_DRAFT_STATES = ("Draft", "Rejected")


def draft_states():
	raw = frappe.db.get_single_value(SETTINGS, "draft_workflow_states") or "\n".join(DEFAULT_DRAFT_STATES)
	return {line.strip() for line in raw.splitlines() if line.strip()}


def in_review(doc):
	"""Unsubmitted, but past the workflow's draft states (pending approval, approved)."""
	from frappe.model.workflow import get_workflow_name

	if doc.docstatus != 0 or not get_workflow_name(doc.doctype):
		return False
	return (doc.get("workflow_state") or "") not in draft_states()


def bound_version(doctype, name):
	"""The newest version built on this document."""
	found = frappe.db.get_value(VERSION, {"source_doctype": doctype, "source_name": name}, "name", order_by="version_no desc")
	return frappe.get_doc(VERSION, found) if found else None


def lock(version, kind, reason, **values):
	version.flags.allow_frozen_write = True
	version.flags.ignore_permissions = True
	version.update({"status": "Frozen", "lock_kind": kind, "lock_reason": reason, **values})
	if not version.frozen_on:
		version.frozen_by, version.frozen_on = frappe.session.user, now_datetime()
	version.save()
	return version


def unlock(version, note):
	version.flags.allow_frozen_write = True
	version.flags.ignore_permissions = True
	version.update({"status": "Working", "lock_kind": None, "lock_reason": None, "frozen_by": None, "frozen_on": None})
	version.save()
	version.add_comment("Info", note)
	return version


def document_changed(doc):
	"""A draft Quotation / Sales Order was saved: its workflow state may have moved into or out of review."""
	version = bound_version(doc.doctype, doc.name)
	if not version or doc.docstatus != 0:
		return
	state = doc.get("workflow_state") or ""
	if in_review(doc):
		reason = _("{0} {1}").format(_(doc.doctype), state.lower())
		if version.status == "Working":
			lock(version, "Review", reason)
		elif version.lock_kind == "Review" and version.lock_reason != reason:
			version.db_set("lock_reason", reason, update_modified=False)
	elif version.status == "Frozen" and version.lock_kind == "Review":
		unlock(version, _("{0} {1} went back to {2}: plan unlocked, its approval no longer applies").format(_(doc.doctype), doc.name, state or _("draft")))


def quotation_submitted(doc):
	"""The offer is out: its version is kept as Round N."""
	version = bound_version("Quotation", doc.name)
	if not version or version.lock_kind == "Round":
		return
	last = frappe.db.sql(f"select max(round_no) from `tab{VERSION}` where planning=%s", version.planning)[0][0] or 0
	n = last + 1
	lock(version, "Round", _("Round {0} · sent to client").format(n), round_no=n, version_name=_("Round {0}").format(n))


def sales_order_submitted(doc):
	"""The job is won: its version is the Agreed budget, and the job gets its Project."""
	version = bound_version("Sales Order", doc.name)
	if version and version.lock_kind != "Agreed":
		lock(version, "Agreed", _("Agreed with client · {0}").format(doc.name), version_name=_("Agreed budget"))
	ensure_project(doc)


def ensure_project(order):
	"""One Project per won Sales Order (it links itself to the plan through its own after_insert)."""
	if order.get("project") or frappe.db.exists("Project", {"sales_order": order.name}):
		return  # a variation order runs on the job's existing Project
	frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": f"{order.customer_name or order.customer} - {order.name}",
			"company": order.company,
			"customer": order.customer,
			"sales_order": order.name,
			"expected_start_date": order.get("delivery_date") or order.transaction_date,
		}
	).insert(ignore_permissions=True)


def supersede(version, by):
	"""An older working version that a newer one continues: keep it, locked, as history."""
	if version.status == "Working":
		lock(version, "Superseded", _("Continued in {0}").format(by))


def catch_up(doctype, name):
	"""A plan opened on a document that is already in review or submitted starts in the right state."""
	doc = frappe.get_doc(doctype, name)
	if doc.docstatus == 1:
		(quotation_submitted if doctype == "Quotation" else sales_order_submitted)(doc)
	elif doc.docstatus == 0:
		document_changed(doc)
