import frappe
from frappe import _
from frappe.model.document import Document


class CommercialPlanningSettings(Document):
	def validate(self):
		seen = set()
		for row in self.divisions:
			if row.supplier in seen:
				frappe.throw(_("Supplier {0} is listed for more than one division").format(row.supplier))
			seen.add(row.supplier)
			if frappe.db.get_value("Supplier", row.supplier, "is_internal_supplier"):
				frappe.throw(_("{0} is an internal (inter-company) supplier; divisions use a plain supplier record").format(row.supplier))
