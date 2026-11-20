"""v2 sourcing: price cost lines (package, LTA, RFQ quotes), push the price to the client Quotation,
raise Purchase Orders from the Sales Order, and settle internal division work with a Journal Entry.

Accounting model: one company; divisions are plain Supplier records mapped to cost centers in
Commercial Planning Settings. The client is invoiced gross on the lead cost center. A division PO
never becomes a Purchase Invoice: it is closed and a cost-center Journal Entry moves the charge."""

import frappe
from frappe import _
from frappe.utils import add_days, flt, nowdate

from commercial_planning.services import actuals, permissions, quote_sync, selling, tree

VERSION = "Commercial Planning Version"
PLAN = "Commercial Planning"
SETTINGS = "Commercial Planning Settings"
ROW_FIELDS = (
	"row_key", "parent_key", "row_type", "description", "item_code", "supplier", "qty", "uom",
	"unit_cost", "exchange_rate", "cost_amount", "selling_amount", "cost_source", "pricing_basis",
	"client_pricing", "markup_pct", "cost_center", "rfq", "supplier_quotation", "purchase_order", "settlement",
)


# ------------------------------------------------------------------ helpers
def settings():
	return frappe.get_single(SETTINGS)


def divisions(conf=None):
	"""{supplier: cost_center} for the internal divisions."""
	return {row.supplier: row.cost_center for row in (conf or settings()).divisions}


def cost_center_for(supplier, conf=None):
	conf = conf or settings()
	return divisions(conf).get(supplier) or conf.lead_cost_center


def cost_lines(version, row_keys=None):
	keys = set(row_keys or [])
	return [row for row in version.items if row.row_type == tree.COST_ITEM and (not keys or row.row_key in keys)]


def set_links(row, **values):
	"""ERP links are bookkeeping, not plan edits: written directly so frozen versions keep them too."""
	frappe.db.set_value("Commercial Planning Item", row.name, values, update_modified=False)
	row.update(values)


def item_for(row, conf):
	code = row.item_code or conf.default_service_item
	if not code:
		frappe.throw(_("Line {0} has no item. Set an item on it or a Default Service Item in Commercial Planning Settings").format(row.description))
	return code


def check_distinct_items(rows, conf, document):
	"""ERPNext refuses a repeated item on one RFQ/PO unless Buying Settings allows it: say which lines clash."""
	if frappe.db.get_single_value("Buying Settings", "allow_multiple_items"):
		return
	seen = {}
	for row in rows:
		seen.setdefault(row.item_code or conf.default_service_item, []).append(row.description)
	clashes = {item: names for item, names in seen.items() if len(names) > 1}
	if clashes:
		detail = "; ".join(f"{item}: {', '.join(names)}" for item, names in clashes.items())
		frappe.throw(
			_("These lines would put the same item on one {0} ({1}). Give each line its own item, or tick Allow Multiple Items in Buying Settings.").format(document, detail)
		)


def load(version_name, write=False):
	version = frappe.get_doc(VERSION, version_name)
	permissions.require(permissions.can_view_plans(), _("You do not have access to Commercial Planning"))
	version.check_permission("read")
	if write:
		permissions.require_edit(version)
	return version, frappe.get_doc(PLAN, version.planning)


def require_setting(conf, *fields):
	missing = [conf.meta.get_label(field) for field in fields if not conf.get(field)]
	if missing:
		frappe.throw(_("Set {0} in Commercial Planning Settings first").format(", ".join(missing)))


# --------------------------------------------------------------- read model
def get_sourcing(version_name):
	version, plan = load(version_name)
	conf = settings()
	internal = divisions(conf)
	view = tree.Tree(version)
	rfq_of = rfq_parents(version)
	rows = []
	for row in view.ordered():
		data = {field: row.get(field) for field in ROW_FIELDS}
		data["rfqs"] = sorted({rfq_of[item] for item in rfq_items_of(row) if item in rfq_of})
		data["depth"] = view.depth(row.row_key) - 1
		data["internal"] = bool(row.supplier and row.supplier in internal)
		data["planned_cost_center"] = row.cost_center or (cost_center_for(row.supplier, conf) if row.row_type == tree.COST_ITEM else None)
		rows.append(data)
	return {
		"version": version.name,
		"status": version.status,
		"editable": permissions.can_edit_version(version),
		"source_doctype": version.source_doctype,
		"quotation": quotation_state(version, plan),
		"plan": {
			"name": plan.name,
			"company": plan.company,
			"quotation": plan.quotation,
			"quotation_docstatus": frappe.db.get_value("Quotation", plan.quotation, "docstatus") if plan.quotation else None,
			"sales_order": plan.sales_order,
			"sales_order_docstatus": frappe.db.get_value("Sales Order", plan.sales_order, "docstatus") if plan.sales_order else None,
			"project": plan.project,
		},
		"settings": {
			"lead_cost_center": conf.lead_cost_center,
			"lta_price_list": conf.lta_price_list,
			"ready": bool(conf.lead_cost_center and conf.internal_charge_account and conf.internal_income_account),
		},
		"divisions": [{"division": d.division_name, "supplier": d.supplier, "cost_center": d.cost_center} for d in conf.divisions],
		"rows": rows,
		"quotes": quotes_by_row(version),
		"bidders": bidders(sorted(set(rfq_of.values()))),
		"purchase_orders": purchase_orders(rows),
		"cost_centers": cost_center_summary(version, rows, conf),
	}


def rfq_items_of(row):
	"""Every RFQ row a line was sent on (a line can go out again to more vendors); older lines hold one."""
	items = [name for name in (row.get("rfq_items") or "").split(",") if name]
	return items or ([row.rfq_item] if row.get("rfq_item") else [])


def rfq_parents(version):
	"""{RFQ item: RFQ} for every RFQ row the version's lines were sent on."""
	items = [item for row in version.items for item in rfq_items_of(row)]
	if not items:
		return {}
	return {r.name: r.parent for r in frappe.get_all("Request for Quotation Item", {"name": ["in", items]}, ["name", "parent"])}


def bidders(rfqs):
	"""One column per supplier invited on these RFQs. Under each RFQ: the supplier's bids on it, newest first;
	the newest is the current bid, older ones were revised. The vendor's total adds up its current bids."""
	if not rfqs:
		return []
	invited = frappe.get_all(
		"Request for Quotation Supplier", {"parent": ["in", rfqs]}, ["supplier", "parent as rfq", "quote_status"], order_by="idx asc"
	)
	quotes = frappe.db.sql(
		"""select distinct p.name, p.supplier, i.request_for_quotation as rfq, p.docstatus, p.grand_total, p.currency,
			p.transaction_date, p.valid_till, p.creation
		from `tabSupplier Quotation` p join `tabSupplier Quotation Item` i on i.parent = p.name
		where i.request_for_quotation in %(rfqs)s and p.docstatus < 2
		order by p.creation desc""",
		{"rfqs": tuple(rfqs)},
		as_dict=True,
	)
	files = {}
	if quotes:
		for f in frappe.get_all(
			"File",
			{"attached_to_doctype": "Supplier Quotation", "attached_to_name": ["in", list({q.name for q in quotes})]},
			["attached_to_name", "file_name", "file_url"],
		):
			files.setdefault(f.attached_to_name, []).append({"file_name": f.file_name, "file_url": f.file_url})
	bids = {}
	for quote in quotes:
		bids.setdefault((quote.supplier, quote.rfq), []).append({**quote, "total": flt(quote.grand_total), "attachments": files.get(quote.name, [])})
	internal = divisions()
	sent = {
		rfq.name: rfq
		for rfq in frappe.get_all("Request for Quotation", {"name": ["in", rfqs]}, ["name", "transaction_date", "docstatus", "status"])
	}
	columns = {}
	for row in invited:
		column = columns.setdefault(row.supplier, {"supplier": row.supplier, "internal": row.supplier in internal, "rfqs": [], "rfq_docs": []})
		column["rfqs"].append(row.rfq)
		if row.rfq in sent:
			column["rfq_docs"].append({**sent[row.rfq], "quote_status": row.quote_status, "bids": bids.get((row.supplier, row.rfq), [])})
	for column in columns.values():
		current = [doc["bids"][0] for doc in column["rfq_docs"] if doc["bids"]]
		column.update(
			current=[bid["name"] for bid in current],
			all_bids=[bid["name"] for doc in column["rfq_docs"] for bid in doc["bids"]],
			total=sum(bid["total"] for bid in current) if current else None,
			currency=current[0]["currency"] if current else None,
		)
	return list(columns.values())


def purchase_orders(rows):
	"""{name: {supplier, status, docstatus, grand_total}} for the POs raised from the plan's lines."""
	names = sorted({row["purchase_order"] for row in rows if row.get("purchase_order")})
	if not names:
		return {}
	return {
		po.name: po
		for po in frappe.get_all(
			"Purchase Order", {"name": ["in", names]}, ["name", "supplier", "status", "docstatus", "grand_total", "transaction_date"]
		)
	}


def quotes_by_row(version):
	"""Supplier Quotation lines answering each cost line's RFQ item (draft and submitted), cheapest first.
	A supplier's revised bid replaces its earlier ones on the same RFQ item."""
	by_item = {item: row.row_key for row in version.items for item in rfq_items_of(row)}
	if not by_item:
		return {}
	found = frappe.db.sql(
		"""select i.request_for_quotation_item as rfq_item, i.parent as supplier_quotation, i.base_rate as rate,
			p.supplier, p.docstatus
		from `tabSupplier Quotation Item` i join `tabSupplier Quotation` p on p.name = i.parent
		where i.request_for_quotation_item in %(items)s and p.docstatus < 2
		order by p.creation desc""",
		{"items": tuple(by_item)},
		as_dict=True,
	)
	newest = {}
	for quote in found:
		newest.setdefault((quote.rfq_item, quote.supplier), quote)
	quotes = {}
	for quote in sorted(newest.values(), key=lambda q: flt(q.rate)):
		quotes.setdefault(by_item[quote.rfq_item], []).append(quote)
	return quotes


# -------------------------------------------------------------- bid entry
def bid_form(version_name, rfq, supplier, revise=None):
	"""What the vendor was asked to price on this RFQ, with the rates of the bid being revised."""
	version, _plan = load(version_name)
	draft = mapped_bid(version, rfq, supplier)
	rates = {}
	if revise:
		check_bid(revise, rfq, supplier)
		rates = dict(frappe.get_all("Supplier Quotation Item", {"parent": revise}, ["request_for_quotation_item", "rate"], as_list=True))
	return {
		"currency": draft.currency,
		"items": [
			{
				"rfq_item": item.request_for_quotation_item,
				"item_code": item.item_code,
				"description": item.description,
				"qty": flt(item.qty),
				"uom": item.uom,
				"rate": flt(rates.get(item.request_for_quotation_item)) or None,
			}
			for item in draft.items
		],
	}


def enter_bid(version_name, rfq, supplier, rates, valid_till=None, submit=False, revise=None):
	"""Record a vendor's bid on an RFQ as a Supplier Quotation. Items left without a rate were not quoted.
	A revised bid is a new quotation; the earlier one stays on record."""
	version, _plan = load(version_name)
	frappe.has_permission("Supplier Quotation", "create", throw=True)
	if revise:
		check_bid(revise, rfq, supplier)
	doc = mapped_bid(version, rfq, supplier)
	rates = {key: flt(value) for key, value in (rates or {}).items()}
	if any(rate < 0 for rate in rates.values()):
		frappe.throw(_("Rates cannot be negative"))
	doc.items = [item for item in doc.items if rates.get(item.request_for_quotation_item, 0) > 0]
	if not doc.items:
		frappe.throw(_("Enter a rate for at least one item"))
	for idx, item in enumerate(doc.items, 1):
		item.idx, item.rate = idx, rates[item.request_for_quotation_item]
	if valid_till:
		doc.valid_till = valid_till
	doc.insert()
	if submit:
		doc.submit()
	return doc.name


def mapped_bid(version, rfq, supplier):
	from erpnext.buying.doctype.request_for_quotation.mapper import make_supplier_quotation_from_rfq

	if rfq not in set(rfq_parents(version).values()):
		frappe.throw(_("{0} was not sent from this cost plan").format(rfq))
	if not frappe.db.exists("Request for Quotation Supplier", {"parent": rfq, "supplier": supplier}):
		frappe.throw(_("{0} is not invited on {1}").format(supplier, rfq))
	return make_supplier_quotation_from_rfq(rfq, for_supplier=supplier)


def check_bid(name, rfq, supplier):
	if frappe.db.get_value("Supplier Quotation", name, "supplier") != supplier or not frappe.db.exists(
		"Supplier Quotation Item", {"parent": name, "request_for_quotation": rfq}
	):
		frappe.throw(_("{0} is not {1}'s bid on {2}").format(name, supplier, rfq))


def cost_center_summary(version, rows, conf):
	"""Planned P&L per cost center: lead earns the client price and carries every cost;
	each division earns its lines' cost as internal income (its own spend is outside the plan)."""
	lead = conf.lead_cost_center
	total_cost = sum(flt(row["cost_amount"]) for row in rows if row["row_type"] == tree.COST_ITEM)
	summary = [{"cost_center": lead, "kind": "Lead", "revenue": flt(version.total_selling), "cost": total_cost}]
	internal = divisions(conf)
	for supplier, center in internal.items():
		income = sum(flt(row["cost_amount"]) for row in rows if row["row_type"] == tree.COST_ITEM and row["supplier"] == supplier)
		if income:
			summary.append({"cost_center": center, "kind": "Division", "revenue": income, "cost": 0})
	return summary


# -------------------------------------------------------------- LTA prices
def lta_rate(price_list, item_code, supplier):
	if not item_code:
		return None
	base = {"price_list": price_list, "item_code": item_code}
	for filters in ({**base, "supplier": supplier}, {**base, "supplier": ["is", "not set"]}) if supplier else ({**base, "supplier": ["is", "not set"]},):
		rate = frappe.db.get_value("Item Price", filters, "price_list_rate")
		if rate is not None:
			return flt(rate)
	return None


# ---------------------------------------------------------------------- RFQ
def send_rfq(version_name, row_keys, suppliers, message=None):
	"""One Request for Quotation for the chosen lines, to internal and/or external suppliers."""
	version, plan = load(version_name)
	frappe.has_permission("Request for Quotation", "create", throw=True)
	rows = cost_lines(version, row_keys)
	if not rows:
		frappe.throw(_("Choose the cost lines to quote"))
	if not suppliers:
		frappe.throw(_("Choose at least one supplier"))
	conf = settings()
	check_distinct_items(rows, conf, _("Request for Quotation"))
	due = add_days(nowdate(), 7)
	rfq = frappe.get_doc(
		{
			"doctype": "Request for Quotation",
			"company": plan.company,
			"transaction_date": nowdate(),
			"schedule_date": due,
			"message_for_supplier": message or _("Please quote for {0}").format(plan.title),
			"suppliers": [{"supplier": supplier, "send_email": 0} for supplier in dict.fromkeys(suppliers)],
			"items": [rfq_item(row, conf, due, plan) for row in rows],
		}
	)
	rfq.insert()
	rfq.submit()
	for row, item in zip(rows, rfq.items):
		# a line sent out for bids is priced from a bid; earlier RFQs stay listed so their bids stay comparable
		set_links(row, rfq=rfq.name, rfq_item=item.name, rfq_items=",".join(rfq_items_of(row) + [item.name]), pricing_basis="Requirement")
	return rfq.name


def line_units(row, doctype):
	"""qty for a vendor document: qty x days, with production's Quantity / Number of Days where present."""
	from commercial_planning.services.quote_sync import has_unit_fields

	qty, days = flt(row.qty) or 1, flt(row.days) or 1
	values = {"qty": qty * days}
	if has_unit_fields(doctype):
		values.update(quantity=qty, number_of_days=days, number_of_pages=1)
	return values


def rfq_item(row, conf, due, plan):
	code = item_for(row, conf)
	uom = frappe.get_cached_value("Item", code, "stock_uom")
	return {
		"item_code": code,
		"description": row.description,
		**line_units(row, "Request for Quotation Item"),
		"uom": uom,
		"stock_uom": uom,
		"conversion_factor": 1,
		"schedule_date": due,
		"project_name": plan.project,
	}


def pull_quotes(version_name):
	"""Price each quoted line from its Supplier Quotations: the line's chosen supplier, else the lowest."""
	version, _plan = load(version_name, write=True)
	quotes = quotes_by_row(version)
	updated = []
	for row in cost_lines(version):
		options = quotes.get(row.row_key)
		if not options:
			continue
		chosen = next((q for q in options if q.supplier == row.supplier), None) if row.supplier else None
		apply_quote(row, chosen or options[0])
		updated.append(row.description)
	if updated:
		version.save()
	return {"updated": updated}


def apply_quote(row, quote):
	row.unit_cost, row.exchange_rate = flt(quote.rate), 1
	row.supplier, row.supplier_quotation, row.cost_source = quote.supplier, quote.supplier_quotation, "Supplier Quotation"


def select_quote(version_name, row_key, supplier_quotation):
	"""The buyer picks a quote for a line: the line takes its price, and a draft quote is submitted (accepted)."""
	version, _plan = load(version_name, write=True)
	quote = next((q for q in quotes_by_row(version).get(row_key, []) if q.supplier_quotation == supplier_quotation), None)
	if not quote:
		frappe.throw(_("{0} does not quote this line").format(supplier_quotation))
	row = tree.Tree(version).get(row_key)
	apply_quote(row, quote)
	version.save()
	if quote.docstatus == 0:
		frappe.get_doc("Supplier Quotation", supplier_quotation).submit()
	return {"row": row.description, "supplier": quote.supplier, "rate": quote.rate}


def is_planner_rfq(rfqs, rfq_items):
	"""Was this RFQ sent from a plan? (Its latest RFQ is on the line; earlier ones are in rfq_items.)"""
	if frappe.db.exists("Commercial Planning Item", {"rfq": ["in", list(rfqs)]}):
		return True
	return any(frappe.db.exists("Commercial Planning Item", {"rfq_items": ["like", f"%{item}%"]}) for item in rfq_items)


def validate_supplier_quotation(doc):
	"""Quotes against a planner RFQ price the RFQ's item list exactly: no extra items, same item and qty."""
	rfqs = {row.request_for_quotation for row in doc.items if row.get("request_for_quotation")}
	if not rfqs or not is_planner_rfq(rfqs, {row.get("request_for_quotation_item") for row in doc.items} - {None}):
		return
	asked = {
		item.name: item
		for item in frappe.get_all(
			"Request for Quotation Item", {"parent": ["in", list(rfqs)]}, ["name", "item_code", "qty"]
		)
	}
	problems = []
	for row in doc.items:
		source = asked.get(row.get("request_for_quotation_item"))
		if not source:
			problems.append(_("Row {0}: {1} is not on the Request for Quotation").format(row.idx, row.item_code))
		elif row.item_code != source.item_code or flt(row.qty) != flt(source.qty):
			problems.append(_("Row {0}: item and quantity must stay as requested ({1} x {2})").format(row.idx, source.item_code, source.qty))
	if problems:
		frappe.throw("<br>".join(problems), title=_("Quote only the requested items"))


# ------------------------------------------------------- client quotation
# Quotation lifecycle: while it is a draft (not in review), client lines and its items sync both ways
# (services/quote_sync.py); submitted, it is amended in ERPNext and the plan follows with a new version.
LOCKED_STATUSES = ("Ordered", "Partially Ordered", "Lost")


def version_quotation(version, plan):
	if version.source_doctype == "Quotation":
		return version.source_name
	return plan.quotation


def quotation_state(version, plan):
	name = version_quotation(version, plan)
	if not name:
		return None
	docstatus, status = frappe.db.get_value("Quotation", name, ["docstatus", "status"])
	amended_to = frappe.db.get_value("Quotation", {"amended_from": name, "docstatus": ["<", 2]}, "name") if docstatus == 2 else None
	syncing = version.source_doctype == "Quotation" and bool(quote_sync.active_quotation(version))
	return {"name": name, "docstatus": docstatus, "status": status, "amended_to": amended_to, "syncing": syncing}


def quotation_info(version_name):
	"""Header state for the plan: which quotation this version prices and what can be done with it."""
	version, plan = load(version_name)
	return quotation_state(version, plan)


# --------------------------------------------------------- purchase orders
def orders_for_sales_order(so_name):
	"""Sales Order submitted: raise draft POs from the plan's Sales Order version (quietly skip if nothing to order)."""
	from commercial_planning.services import version as version_service

	plan = version_service.get_plan_for("Sales Order", so_name)
	if not plan:
		return []
	version = frappe.db.get_value(
		VERSION, {"planning": plan, "source_doctype": "Sales Order", "source_name": so_name}, "name", order_by="version_no desc"
	)
	return create_purchase_orders(version, quiet=True) if version else []


def create_purchase_orders(version_name, submit=False, quiet=False, supplier=None):
	"""Draft (or submitted) Purchase Orders from the Sales Order: one per supplier (or only `supplier`'s), each line
	on its cost center. A line priced from a submitted Supplier Quotation keeps the native link to that quote."""
	version, plan = load(version_name)
	if not plan.sales_order or frappe.db.get_value("Sales Order", plan.sales_order, "docstatus") != 1:
		frappe.throw(_("Purchase Orders are raised once the client's Sales Order is submitted"))
	if submit and version.is_revision and version.revision_status != "Approved":
		submit = False  # costs from an unapproved revision stay on draft POs until it is approved
		frappe.msgprint(_("This revision is not approved yet, so its Purchase Orders stay draft"), alert=True)
	by_supplier = {}
	for row in cost_lines(version):
		if row.supplier and flt(row.unit_cost) > 0 and not row.purchase_order and supplier in (None, row.supplier):
			by_supplier.setdefault(row.supplier, []).append(row)
	if not by_supplier:
		if quiet:
			return []
		frappe.throw(_("No priced lines with a supplier are waiting for a Purchase Order"))
	frappe.has_permission("Purchase Order", "create", throw=True)
	conf = settings()
	require_setting(conf, "lead_cost_center")
	for rows in by_supplier.values():
		check_distinct_items(rows, conf, _("Purchase Order"))
	created = []
	for supplier, rows in by_supplier.items():
		center = cost_center_for(supplier, conf)
		po = frappe.get_doc(
			{
				"doctype": "Purchase Order",
				"company": plan.company,
				"supplier": supplier,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 7),
				"project": plan.project,
				"items": [po_item(row, conf, center, plan) for row in rows],
			}
		)
		po.insert()
		if submit:
			po.submit()
		for row, item in zip(rows, po.items):  # PO rows are built in line order
			set_links(row, purchase_order=po.name, po_item=item.name, cost_center=center)
		created.append({"purchase_order": po.name, "supplier": supplier, "internal": supplier in divisions(conf), "total": po.grand_total})
	if submit:
		actuals.sync(plan.name)  # the PO's submit event ran before the lines pointed at it
	return created


def po_item(row, conf, center, plan):
	code = item_for(row, conf)
	uom = frappe.get_cached_value("Item", code, "stock_uom")
	item = {
		"item_code": code,
		"description": row.description,
		**line_units(row, "Purchase Order Item"),
		"uom": uom,
		"stock_uom": uom,
		"conversion_factor": 1,
		"rate": flt(row.unit_cost) * (flt(row.exchange_rate) or 1),
		"schedule_date": add_days(nowdate(), 7),
		"cost_center": center,
		"project": plan.project,
	}
	quote = row.supplier_quotation
	if quote and rfq_items_of(row) and frappe.db.get_value("Supplier Quotation", quote, "docstatus") == 1:
		item["supplier_quotation"] = quote
		item["supplier_quotation_item"] = frappe.db.get_value(
			"Supplier Quotation Item", {"parent": quote, "request_for_quotation_item": ["in", rfq_items_of(row)]}, "name"
		)
	return item


# ------------------------------------------------------ internal settlement
def settle_internal(version_name):
	"""For each submitted division PO: post the cost-center Journal Entry and close the PO."""
	from erpnext.buying.doctype.purchase_order.purchase_order import update_status

	version, plan = load(version_name)
	frappe.has_permission("Journal Entry", "create", throw=True)
	conf = settings()
	require_setting(conf, "lead_cost_center", "internal_charge_account", "internal_income_account")
	internal = divisions(conf)
	by_po = {}
	for row in cost_lines(version):
		if row.purchase_order and not row.settlement and row.supplier in internal:
			by_po.setdefault(row.purchase_order, []).append(row)
	settled, waiting = [], []
	for po_name, rows in by_po.items():
		po = frappe.get_doc("Purchase Order", po_name)
		if po.docstatus != 1:
			waiting.append(po_name)
			continue
		je = settlement_entry(po, plan, conf, internal[po.supplier])
		update_status("Closed", po.name)
		for row in rows:
			set_links(row, settlement=je.name)
		settled.append({"purchase_order": po.name, "journal_entry": je.name, "amount": po.base_net_total})
	if settled:
		actuals.sync(plan.name)  # the JE's submit event ran before the lines pointed at it
	return {"settled": settled, "waiting_submit": waiting}


def settlement_entry(po, plan, conf, division_center):
	amount = flt(po.base_net_total)
	je = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": po.company,
			"posting_date": nowdate(),
			"user_remark": _("Internal transfer for {0} ({1}), plan {2}").format(po.name, po.supplier, plan.name),
			"accounts": [
				{"account": conf.internal_charge_account, "debit_in_account_currency": amount,
				 "cost_center": conf.lead_cost_center, "project": plan.project},
				{"account": conf.internal_income_account, "credit_in_account_currency": amount,
				 "cost_center": division_center, "project": plan.project},
			],
		}
	)
	je.insert()
	je.submit()
	return je
