import frappe


def execute():
	"""v2 phase 2: client lines carry their document item's rate (price per unit per day)."""
	frappe.db.sql(
		"""update `tabCommercial Planning Item` row
		join `tabCommercial Planning Item Link` link on link.parent = row.parent and link.row_key = row.row_key
		join `tabQuotation Item` item on item.name = link.link_name and link.link_doctype = 'Quotation Item'
		set row.rate = item.rate
		where row.row_type = 'Category' and ifnull(row.rate, 0) = 0"""
	)
	frappe.db.sql(
		"""update `tabCommercial Planning Item` row
		join `tabCommercial Planning Item Link` link on link.parent = row.parent and link.row_key = row.row_key
		join `tabSales Order Item` item on item.name = link.link_name and link.link_doctype = 'Sales Order Item'
		set row.rate = item.rate
		where row.row_type = 'Category' and ifnull(row.rate, 0) = 0"""
	)
