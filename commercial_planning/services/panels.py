"""Document panels: a few header fields and the workflow actions of a linked document, without leaving the planner.

Only the fields listed here can be read or written. Items are not edited in a panel (client lines are the
planner grid). The user's own permissions apply; Desk client scripts do not run here, so the ones production
relies on for these fields are repeated in `before_save`."""

import frappe
from frappe import _
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name

PANELS = {
	"Quotation": {"fields": ("custom_title", "title", "valid_till", "event_date", "event_location"), "totals": True},
	"Sales Order": {"fields": ("delivery_date", "po_no", "po_date"), "totals": True},
	"Request for Quotation": {"fields": ("schedule_date", "message_for_supplier"), "parties": "suppliers"},
	"Supplier Quotation": {"fields": ("valid_till",), "totals": True},
	"Purchase Order": {"fields": ("schedule_date",), "totals": True},
	"Project": {"fields": ("expected_start_date", "expected_end_date", "status", "priority"), "totals": False},
}
INPUT_TYPES = {"Data", "Date", "Datetime", "Select", "Small Text", "Text", "Float", "Int", "Currency", "Percent", "Check"}


def spec(doctype):
	found = PANELS.get(doctype)
	if not found:
		frappe.throw(_("{0} has no panel; open it in Desk").format(doctype))
	return found


def get_panel(doctype, name):
	conf = spec(doctype)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	meta = frappe.get_meta(doctype)
	can_write = doc.has_permission("write")
	fields = []
	for fieldname in conf["fields"]:
		if fieldname == "title" and meta.has_field("custom_title"):
			continue  # production titles quotations with its own field
		df = meta.get_field(fieldname)
		if not df or df.fieldtype not in INPUT_TYPES or df.hidden:
			continue
		editable = can_write and not df.read_only and (doc.docstatus == 0 or df.allow_on_submit) and doc.docstatus < 2
		fields.append({"fieldname": fieldname, "label": _(df.label), "fieldtype": df.fieldtype, "options": df.options,
			"value": doc.get(fieldname), "editable": bool(editable)})
	return {
		"doctype": doctype,
		"name": name,
		"title": doc.get("title") or doc.get("customer_name") or doc.get("supplier_name") or doc.get("project_name") or name,
		"status": doc.get("status"),
		"docstatus": doc.docstatus,
		"workflow_state": doc.get("workflow_state") if get_workflow_name(doctype) else None,
		"fields": fields,
		"totals": totals(doc) if conf.get("totals") else None,
		"parties": [row.get("supplier") for row in doc.get(conf["parties"])] if conf.get("parties") else None,
		"actions": actions(doc),
		"modified": str(doc.modified),
	}


def totals(doc):
	return {"currency": doc.get("currency"), "net_total": doc.get("net_total"), "grand_total": doc.get("grand_total")}


def actions(doc):
	"""What the user may do next: the workflow's transitions, else Submit on a draft they may submit."""
	if get_workflow_name(doc.doctype):
		return [t.action for t in get_transitions(doc)]
	if doc.docstatus == 0 and frappe.get_meta(doc.doctype).is_submittable and doc.has_permission("submit"):
		return [_("Submit")]
	return []


def save_panel(doctype, name, values, modified=None):
	conf = spec(doctype)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("write")
	if modified and str(doc.modified) != str(modified):
		frappe.throw(_("{0} was changed by someone else. Reload the panel and try again.").format(name), frappe.TimestampMismatchError)
	allowed = {f["fieldname"] for f in get_panel(doctype, name)["fields"] if f["editable"]}
	unknown = set(values) - allowed
	if unknown:
		frappe.throw(_("These fields cannot be changed here: {0}").format(", ".join(sorted(unknown))))
	doc.update({key: value for key, value in values.items() if key in conf["fields"]})
	before_save(doc)
	doc.save()
	return get_panel(doctype, name)


def before_save(doc):
	"""Production's Desk scripts for these fields, done on the server because they do not run in a panel."""
	if doc.doctype == "Quotation" and doc.meta.has_field("custom_title"):
		if not doc.custom_title or doc.custom_title == "{customer_name}":
			doc.custom_title = doc.customer_name  # "Auto Fetch for Qoutation Title"
	if doc.doctype == "Sales Order" and doc.delivery_date:
		for item in doc.items:  # "Sales Order-delivery date error"
			item.delivery_date = doc.delivery_date


def run_action(doctype, name, action):
	spec(doctype)
	doc = frappe.get_doc(doctype, name)
	if action not in actions(doc):
		frappe.throw(_("{0} is not possible on {1} now").format(action, name))
	if get_workflow_name(doctype):
		apply_workflow(doc, action)
	else:
		doc.submit()
	return get_panel(doctype, name)
