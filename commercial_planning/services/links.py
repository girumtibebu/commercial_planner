"""Which plan a Desk document belongs to: the plan's own Quotation, Sales Order and Project, the documents the planner
raised (RFQs, bids, POs, settlements, variation orders), and any document that points at one of those."""

import frappe

from commercial_planning.services.version import PLAN_FIELD, get_plan_for

VERSION = "Commercial Planning Version"
LINE_FIELDS = {
	"Request for Quotation": "rfq",
	"Supplier Quotation": "supplier_quotation",
	"Purchase Order": "purchase_order",
	"Journal Entry": "settlement",
	"Sales Order": "variation_order",
}
# fields on a document or its rows that point at a document the plan knows
REFERENCES = (
	("project", "Project"),
	("parent_project", "Project"),
	("project_name", "Project"),
	("sales_order", "Sales Order"),
	("against_sales_order", "Sales Order"),
	("prevdoc_docname", "Quotation"),
	("request_for_quotation", "Request for Quotation"),
	("supplier_quotation", "Supplier Quotation"),
	("purchase_order", "Purchase Order"),
	("purchase_invoice", "Purchase Invoice"),
	("sales_invoice", "Sales Invoice"),
)
MAX_HOPS = 2  # e.g. Payment Entry -> Purchase Invoice -> Purchase Order


def find_plan(doctype, name, hops=0):
	if doctype in PLAN_FIELD:
		plan = get_plan_for(doctype, name)
		if plan:
			return plan
	plan = from_lines(doctype, name)
	if plan or doctype in PLAN_FIELD or hops >= MAX_HOPS or not frappe.db.exists(doctype, name):
		return plan  # the plan's own documents are linked directly or not at all
	doc = frappe.get_doc(doctype, name)
	for target, value in references(doc):
		if (target, value) != (doctype, name):
			plan = find_plan(target, value, hops + 1)
			if plan:
				return plan
	return None


def from_lines(doctype, name):
	field = LINE_FIELDS.get(doctype)
	if not field:
		return None
	found = frappe.db.sql(
		f"""select ver.planning from `tabCommercial Planning Item` item join `tab{VERSION}` ver on ver.name = item.parent
		where item.`{field}` = %s limit 1""",
		name,
	)
	return found[0][0] if found else None


def references(doc):
	"""(doctype, name) pairs the document and its rows point at, header first, without repeats."""
	seen = []
	for row in [doc, *doc.get_all_children()]:
		pairs = [(target, row.get(field)) for field, target in REFERENCES]
		for kind, value in (("reference_doctype", "reference_name"), ("reference_type", "reference_name")):
			pairs.append((row.get(kind), row.get(value)))
		for pair in pairs:
			if pair[0] and pair[1] and isinstance(pair[1], str) and pair not in seen:
				seen.append(pair)
	return seen
