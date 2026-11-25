"""Document events: keep plans connected to the documents they follow. Never block the document."""

import frappe

from commercial_planning.services import version as version_service


def guarded(action):
	"""Run `action`; on failure log it instead of breaking Quotation / Sales Order saving (raise in tests)."""
	try:
		action()
	except Exception:
		if frappe.flags.in_test:
			raise
		frappe.log_error(title="Commercial Planning could not follow a document")


def is_variation(doc):
	from commercial_planning.services import revisions

	return bool(doc.flags.cp_variation) or revisions.is_variation(doc.name)


def sales_order_created(doc, method=None):
	if is_variation(doc):
		return  # a variation of a won job: it belongs to that plan already
	guarded(lambda: version_service.link_sales_order(doc.name))


def document_changed(doc, method=None):
	"""Quotation / Sales Order saved while unsubmitted: its workflow may have moved into or out of review."""
	from commercial_planning.services import lifecycle

	if doc.doctype == "Sales Order" and is_variation(doc):
		return
	if doc.docstatus == 0:  # a Quotation's changes wait for the planner's Sync button; see sync_status
		guarded(lambda: lifecycle.document_changed(doc))


def quotation_submitted(doc, method=None):
	from commercial_planning.services import lifecycle

	guarded(lambda: lifecycle.quotation_submitted(doc))


def sales_order_submitted(doc, method=None):
	from commercial_planning.services import lifecycle, sourcing

	if is_variation(doc):
		guarded(lambda: variation_submitted(doc))
		return
	guarded(lambda: lifecycle.sales_order_submitted(doc))  # Agreed budget + Project first
	guarded(lambda: sourcing.orders_for_sales_order(doc.name))


def variation_submitted(doc):
	"""A billed variation was agreed: note it on the plan (the Agreed totals read it from the order)."""
	plan = doc.project and frappe.db.get_value("Commercial Planning", {"project": doc.project}, "name")
	if plan:
		frappe.get_doc("Commercial Planning", plan).add_comment("Info", f"Variation {doc.name} agreed with the client ({doc.net_total})")


def cost_document_changed(doc, method=None):
	"""A PO, Purchase Invoice or Journal Entry was submitted or cancelled: refresh the plans it touches."""
	from commercial_planning.services import actuals

	guarded(lambda: actuals.sync_for_document(doc))


def supplier_quotation_validate(doc, method=None):
	"""The one rule here that blocks on purpose: quotes against a planner RFQ keep its item list."""
	from commercial_planning.services import sourcing

	sourcing.validate_supplier_quotation(doc)


def project_created(doc, method=None):
	guarded(lambda: version_service.link_project(doc.name))


def quotation_created(doc, method=None):
	if doc.amended_from:
		guarded(lambda: version_service.follow_amendment(doc.name))
