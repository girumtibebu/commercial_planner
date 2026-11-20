import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from commercial_planning.api import planning as planning_api
from commercial_planning.tests.test_conversions import sales_order_from, submitted_quotation

VERSION = "Commercial Planning Version"
PLAN = "Commercial Planning"


def make_project(order=None, name="Planning test project"):
	company = frappe.get_all("Company", pluck="name", limit=1)[0]
	data = {"doctype": "Project", "project_name": name, "company": company}
	if order:
		data.update({"sales_order": order.name, "customer": order.customer})
	return frappe.get_doc(data).insert()


class TestProjects(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def planned_order(self):
		quotation = submitted_quotation()
		plan = planning_api.open_for("Quotation", quotation.name)
		order = sales_order_from(quotation)
		return plan, order

	def test_project_joins_the_plan_without_a_new_version(self):
		plan, order = self.planned_order()
		project = make_project(order)
		self.assertEqual(frappe.db.get_value(PLAN, plan, "project"), project.name)
		self.assertEqual(frappe.db.count(VERSION, {"planning": plan}), 2)  # the Sales Order version stays the budget
		self.assertEqual(planning_api.open_for("Project", project.name), plan)

	def test_submitting_the_sales_order_makes_the_agreed_budget_and_project(self):
		plan, order = self.planned_order()
		order.submit()
		agreed = frappe.get_doc(VERSION, f"{plan}-V02")
		self.assertEqual((agreed.status, agreed.lock_kind, agreed.version_name), ("Frozen", "Agreed", "Agreed budget"))
		project = frappe.db.get_value("Project", {"sales_order": order.name})
		self.assertTrue(project)
		self.assertEqual(frappe.db.get_value(PLAN, plan, "project"), project)
		self.assertEqual(flt(agreed.total_selling), flt(order.net_total))

	def test_project_without_a_sales_order_starts_an_empty_plan(self):
		project = make_project(name="Standalone project")
		plan = planning_api.open_for("Project", project.name)
		plan_doc = frappe.get_doc(PLAN, plan)
		version = frappe.get_doc(VERSION, f"{plan}-V01")
		self.assertEqual((plan_doc.created_from, plan_doc.project), ("Project", project.name))
		self.assertEqual((version.stage, version.purpose, len(version.items)), ("Project", "Budget", 0))

	def test_a_second_project_is_not_attached(self):
		plan, order = self.planned_order()
		first = make_project(order, "First")
		make_project(order, "Second")
		self.assertEqual(frappe.db.get_value(PLAN, plan, "project"), first.name)
		self.assertEqual(frappe.db.count(VERSION, {"planning": plan}), 2)
