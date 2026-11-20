import json

import frappe
from frappe import _

from commercial_planning.services import links, permissions, quote_sync, sync, tree, workspace
from commercial_planning.services import version as version_service

PLAN = "Commercial Planning"
VERSION = "Commercial Planning Version"


def parse_list(value):
	return json.loads(value) if isinstance(value, str) else value


@frappe.whitelist()
def can_open():
	return permissions.can_view_plans()


@frappe.whitelist()
def open_for(doctype, name):
	"""Return the plan a document belongs to. A Quotation, Sales Order or Project gets one on first use;
	any other document opens the plan it references (an RFQ, PO, invoice, delivery, payment...)."""
	permissions.require(permissions.can_view_plans(), _("You do not have access to Commercial Planning"))
	frappe.has_permission(doctype, "read", doc=name, throw=True)
	plan = links.find_plan(doctype, name)
	if doctype not in ("Quotation", "Sales Order", "Project") and not plan:
		frappe.throw(_("{0} {1} is not linked to a Commercial Planning record").format(_(doctype), name))
	if plan:
		frappe.has_permission(PLAN, "read", doc=plan, throw=True)
		return plan
	frappe.has_permission(PLAN, "create", throw=True)
	if doctype == "Sales Order":
		plan = version_service.link_sales_order(name)
	elif doctype == "Project":
		plan = version_service.link_project(name)
	else:
		plan = version_service.create_plan_from_quotation(name)
	if not plan:
		frappe.throw(_("{0} could not be connected to a Commercial Planning record").format(name))
	return plan


@frappe.whitelist()
def plan_for(doctype, name):
	"""For a document form: the plan it is linked to, if the user may open it (else None)."""
	if not permissions.can_view_plans() or not frappe.has_permission(doctype, "read", doc=name):
		return None
	plan = links.find_plan(doctype, name)
	return plan if plan and frappe.has_permission(PLAN, "read", doc=plan) else None


@frappe.whitelist()
def sync_summary(doctype, name):
	"""For a document form: is its plan in sync with the document's items?"""
	if not permissions.can_view_plans():
		return None
	frappe.has_permission(doctype, "read", doc=name, throw=True)
	return sync.sync_summary(doctype, name)


@frappe.whitelist()
def get_workspace(plan, versions=None):
	return workspace.get_workspace(plan, parse_list(versions))


@frappe.whitelist()
def apply_ops(version, ops, expected_modified=None, versions=None):
	"""Apply row operations atomically to one Working version and return the refreshed workspace."""
	doc = frappe.get_doc(VERSION, version)
	permissions.require_edit_ops(doc, parse_list(ops) or [])
	if expected_modified and str(doc.modified) != str(expected_modified):
		frappe.throw(_("This version was changed by someone else. Reload and try again."), frappe.TimestampMismatchError)
	created = tree.apply_ops(doc, parse_list(ops) or [])
	quote_sync.push(doc)  # client lines are the draft Quotation's items: write them through at once
	doc.save(ignore_version=False)  # row edits feed the activity log, also under the test runner
	return {"created": created, "workspace": workspace.get_workspace(doc.planning, parse_list(versions))}


@frappe.whitelist(methods=["POST"])
def save_columns(choice):
	"""The user's grid columns: [{key, width}] in their order."""
	from commercial_planning.services import columns

	return columns.save_choice(parse_list(choice) or [])


@frappe.whitelist(methods=["POST"])
def set_item_field(version, row_key, field, value=None, versions=None):
	"""Write a Quotation Item column (such as a custom field) from the planner to the draft Quotation."""
	from commercial_planning.services import columns

	doc = frappe.get_doc(VERSION, version)
	permissions.require_edit(doc)
	columns.set_item_field(doc, row_key, field, value)
	return {"workspace": workspace.get_workspace(doc.planning, parse_list(versions))}


@frappe.whitelist()
def rental_request(version):
	"""The inventory and small-items request a version's BOQ gives the rental app, plus what it leaves out."""
	from commercial_planning.services import rental_request as request_service

	if not permissions.can_view_plans():
		frappe.throw(_("You cannot view this plan"), frappe.PermissionError)
	return request_service.for_version(frappe.get_doc(VERSION, version))
