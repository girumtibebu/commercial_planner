import frappe


def execute():
	"""'Package' moved from the cost line (where it now reads 'Manual') to the category's Client Price."""
	frappe.db.sql(
		"""update `tabCommercial Planning Item` set pricing_basis = 'Manual'
		where pricing_basis = 'Package' and row_type != 'Category'"""
	)
	frappe.db.sql(
		"""update `tabCommercial Planning Item` set client_pricing = 'Package', pricing_basis = null
		where pricing_basis = 'Package' and row_type = 'Category'"""
	)
	frappe.db.sql(
		"""update `tabCommercial Planning Item` set client_pricing = 'Cost plus'
		where row_type = 'Category' and ifnull(markup_pct, 0) != 0 and ifnull(client_pricing, '') = ''"""
	)
