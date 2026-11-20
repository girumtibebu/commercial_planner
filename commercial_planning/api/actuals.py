import frappe
from frappe import _
from frappe.utils import flt, nowdate

from commercial_planning.services import permissions


@frappe.whitelist(methods=["POST"])
def refresh(plan, versions=None):
	"""Re-read actual and committed cost from ERPNext (also picks up project costs booked elsewhere)."""
	from commercial_planning.services import actuals, workspace

	permissions.require(permissions.can_view_plans(), _("You do not have access to Commercial Planning"))
	frappe.has_permission("Commercial Planning", "read", doc=plan, throw=True)
	actuals.sync(plan)
	return workspace.get_workspace(plan, frappe.parse_json(versions) if versions else None)


@frappe.whitelist()
def add_manual(planning, amount, row_key=None, description=None, basis="Actual", posting_date=None):
	editors = (permissions.PLANNER, permissions.PROJECTS_MANAGER) + permissions.ADMIN_ROLES
	permissions.require(permissions.has_any_role(editors), _("You cannot enter actual costs"))
	entry = frappe.get_doc(
		{
			"doctype": "Commercial Planning Actual",
			"planning": planning,
			"row_key": row_key or None,
			"amount": flt(amount),
			"basis": basis,
			"description": description,
			"posting_date": posting_date or nowdate(),
			"is_manual": 1,
			"provider": "manual",
		}
	)
	return entry.insert().name
