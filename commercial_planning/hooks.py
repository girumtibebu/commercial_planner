app_name = "commercial_planning"
app_title = "Commercial Planning"
app_publisher = "EMC"
app_description = "Spreadsheet-style commercial planning for quotations, sales orders and projects"
app_email = "girumtibebu@gmail.com"
app_license = "mit"

required_apps = ["erpnext"]

app_include_js = "/assets/commercial_planning/js/cp_launcher_v2.js"

doctype_js = {
	"Quotation": "public/js/quotation.js",
	"Sales Order": "public/js/sales_order.js",
	"Project": "public/js/project.js",
}

doc_events = {
	# the plan follows these documents' workflow: review lock / unlock on save, Round / Agreed budget on submit
	"Quotation": {
		"after_insert": "commercial_planning.events.quotation_created",
		"on_update": "commercial_planning.events.document_changed",
		"on_submit": "commercial_planning.events.quotation_submitted",
	},
	"Sales Order": {
		"after_insert": "commercial_planning.events.sales_order_created",
		"on_update": "commercial_planning.events.document_changed",
		"on_submit": "commercial_planning.events.sales_order_submitted",
	},
	"Project": {"after_insert": "commercial_planning.events.project_created"},
	"Supplier Quotation": {"validate": "commercial_planning.events.supplier_quotation_validate"},
	# actual / committed cost of plans follows these documents
	"Purchase Order": {"on_submit": "commercial_planning.events.cost_document_changed", "on_cancel": "commercial_planning.events.cost_document_changed"},
	"Purchase Invoice": {"on_submit": "commercial_planning.events.cost_document_changed", "on_cancel": "commercial_planning.events.cost_document_changed"},
	"Journal Entry": {"on_submit": "commercial_planning.events.cost_document_changed", "on_cancel": "commercial_planning.events.cost_document_changed"},
}

website_route_rules = [
	{"from_route": "/commercial-planning/<path:app_path>", "to_route": "commercial-planning"},
]

before_install = "commercial_planning.install.before_install"
before_migrate = "commercial_planning.install.before_migrate"
after_install = "commercial_planning.install.after_install"
after_migrate = "commercial_planning.install.after_migrate"

# Actual cost providers: dotted paths to callables (plan) -> iterable of ledger dicts.
commercial_planning_actual_providers = []
