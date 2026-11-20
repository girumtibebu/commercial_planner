import frappe
from frappe import _dict
from frappe.tests import IntegrationTestCase

from commercial_planning.services import permissions, pricing, rental_request


def line(cost, **values):
	return _dict(
		{
			"cost_amount": cost,
			"important": 0,
			"line_kind": "Inventory",
			"rental_item": None,
			"qty": 1,
			"days": 1,
			"uom": "Nos",
			"parent_key": "cat",
			"description": "line",
			"variance_qty": 0,
		}
		| values
	)


class TestPricing(IntegrationTestCase):
	def test_only_important_and_sourced_lines_build_the_price(self):
		lines = [
			line(1000, important=1),  # marked by sales
			line(500, line_kind="Sub-hire"),  # sourced: always important
			line(300),  # ordinary inventory: not in the price
			line(200, line_kind="Small item", important=1),  # small items go to the allowance, never the price base
		]
		figures = pricing.price_breakdown(lines, allowance_pct=10, margin_pct=20)
		self.assertEqual(figures["important_cost"], 1500)
		self.assertEqual(figures["allowance_amount"], 150)
		self.assertAlmostEqual(figures["suggested_selling"], (1500 + 150) * 1.2)

	def test_no_important_lines_gives_no_suggestion(self):
		figures = pricing.price_breakdown([line(300)], allowance_pct=10, margin_pct=20)
		self.assertEqual(figures["important_cost"], 0)
		self.assertEqual(figures["suggested_selling"], 0)

	def test_price_within_tolerance_needs_no_reason(self):
		self.assertIsNone(pricing.override_problem(1040, 1000, 5, ""))

	def test_price_outside_tolerance_needs_a_reason(self):
		self.assertIsNotNone(pricing.override_problem(1200, 1000, 5, ""))
		self.assertIsNone(pricing.override_problem(1200, 1000, 5, "Client is a repeat account"))

	def test_no_suggestion_means_nothing_to_check(self):
		self.assertIsNone(pricing.override_problem(900, 0, 5, ""))


class TestRentalRequest(IntegrationTestCase):
	def test_request_groups_booking_small_items_and_leftovers(self):
		lines = [
			line(0, rental_item="LED-P39", qty=20, days=2, uom="Nos", description="LED panel", variance_qty=2),
			line(0, line_kind="Small item", description="Gaffer tape", qty=6),
			line(0, line_kind="Sub-hire", description="Generator", qty=1),
			line(0, description="Crew van hire"),  # no rental item: reported, not booked
		]
		result = rental_request.build_request(lines, {"cat": "Stage"})
		self.assertEqual(result["booking"], [{"category": "Stage", "description": "LED panel", "qty": 22, "days": 2, "uom": "Nos", "item": "LED-P39"}])
		self.assertEqual([row["description"] for row in result["small_items"]], ["Gaffer tape"])
		self.assertEqual(result["unmapped"], ["Crew van hire"])


class TestSalesPermission(IntegrationTestCase):
	def test_marking_important_is_sales_only_work(self):
		self.assertTrue(permissions.is_sales_only([{"op": "update", "row_key": "a", "values": {"important": 1}}]))
		self.assertFalse(permissions.is_sales_only([{"op": "update", "row_key": "a", "values": {"qty": 3}}]))
		self.assertFalse(permissions.is_sales_only([{"op": "update", "values": {"important": 1}}, {"op": "delete", "row_key": "a"}]))
		self.assertFalse(permissions.is_sales_only([]))
