import frappe


def execute():
	"""Cost lines with no Cost From were typed estimates: they are Manual."""
	frappe.db.sql(
		"""update `tabCommercial Planning Item` set pricing_basis = 'Manual'
		where row_type = 'Cost Item' and ifnull(pricing_basis, '') = ''"""
	)
