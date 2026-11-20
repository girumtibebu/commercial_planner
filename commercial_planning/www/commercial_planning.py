import frappe
from frappe import _

from commercial_planning.services import permissions

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to open Commercial Planning"), frappe.PermissionError)
	permissions.require(permissions.can_view_plans(), _("You do not have access to Commercial Planning"))
	frappe.db.commit()
	context.boot = frappe._dict(
		{
			"csrf_token": frappe.sessions.get_csrf_token(),
			"site_name": frappe.local.site,
			"frappe_version": frappe.__version__,
			"user": frappe.session.user,
			"user_fullname": frappe.utils.get_fullname(),
			"desk_theme": frappe.db.get_value("User", frappe.session.user, "desk_theme") or "Light",
			"help_links": get_help_links(),
		}
	)
	return context


def get_help_links():
	"""External links of the standard Help menu (Navbar Settings); Desk pages and actions are left out."""
	items = frappe.get_single("Navbar Settings").help_dropdown
	return [{"label": _(i.item_label), "route": i.route} for i in items if i.item_type == "Route" and (i.route or "").startswith("http") and not i.hidden]
