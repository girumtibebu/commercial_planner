import frappe

from commercial_planning.services import panels


@frappe.whitelist()
def get_panel(doctype, name):
	return panels.get_panel(doctype, name)


@frappe.whitelist(methods=["POST"])
def save_panel(doctype, name, values, modified=None):
	return panels.save_panel(doctype, name, frappe.parse_json(values) or {}, modified)


@frappe.whitelist(methods=["POST"])
def run_action(doctype, name, action):
	return panels.run_action(doctype, name, action)
