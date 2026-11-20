import frappe

VERSION = "Commercial Planning Version"


def execute():
	"""Give locked versions made before v2 phase 1 their meaning: Agreed budget, Round N, or Superseded."""
	versions = frappe.get_all(
		VERSION,
		{"status": ["in", ["Frozen", "Approved"]], "lock_kind": ["is", "not set"]},
		["name", "planning", "version_no", "source_doctype", "source_name"],
		order_by="planning, version_no",
	)
	rounds = {}
	for ver in versions:
		submitted = (
			ver.source_doctype in ("Quotation", "Sales Order")
			and ver.source_name
			and frappe.db.get_value(ver.source_doctype, ver.source_name, "docstatus") in (1, 2)
		)
		if submitted and ver.source_doctype == "Sales Order":
			values = {"lock_kind": "Agreed", "lock_reason": f"Agreed with client · {ver.source_name}"}
		elif submitted:
			rounds[ver.planning] = rounds.get(ver.planning, 0) + 1
			n = rounds[ver.planning]
			values = {"lock_kind": "Round", "round_no": n, "lock_reason": f"Round {n} · sent to client"}
		else:
			values = {"lock_kind": "Superseded", "lock_reason": "Locked before v2"}
		frappe.db.set_value(VERSION, ver.name, values, update_modified=False)
