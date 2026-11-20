import frappe

from commercial_planning.api.planning import parse_list
from commercial_planning.services import version as version_service
from commercial_planning.services import workspace

VERSION = "Commercial Planning Version"


def refreshed(planning, versions):
	return workspace.get_workspace(planning, parse_list(versions))


@frappe.whitelist()
def create(
	planning,
	reason,
	from_version=None,
	template=None,
	version_name=None,
	stage=None,
	purpose=None,
	apply_source_changes=0,
	versions=None,
):
	"""Create a version (copy of `from_version`, defaults from `template`) and return the refreshed workspace."""
	new = version_service.create_version(
		planning,
		from_version=from_version,
		template=template,
		version_name=version_name,
		stage=stage,
		purpose=purpose,
		reason=reason,
		apply_source_changes=bool(int(apply_source_changes or 0)),
	)
	shown = (parse_list(versions) or []) + [new.name] if versions else None
	return {"version": new.name, "workspace": refreshed(planning, shown)}


def _revision(version):
	from commercial_planning.services import permissions

	doc = frappe.get_doc(VERSION, version)
	frappe.has_permission("Commercial Planning", "write", doc=doc.planning, throw=True)
	permissions.require(permissions.can_view_plans(), frappe._("You cannot change budget revisions"))
	return doc


@frappe.whitelist(methods=["POST"])
def submit_revision(version, versions=None):
	"""Check the approval rule: approved at once, or locked until the approver decides."""
	from commercial_planning.services import revisions

	doc = revisions.submit(_revision(version))
	return {"status": doc.revision_status, "workspace": refreshed(doc.planning, versions)}


@frappe.whitelist(methods=["POST"])
def approve_revision(version, versions=None):
	from commercial_planning.services import revisions

	doc = revisions.approve(_revision(version))
	return {"status": doc.revision_status, "workspace": refreshed(doc.planning, versions)}


@frappe.whitelist(methods=["POST"])
def reject_revision(version, reason, versions=None):
	from commercial_planning.services import revisions

	doc = revisions.reject(_revision(version), reason)
	return {"status": doc.revision_status, "workspace": refreshed(doc.planning, versions)}


@frappe.whitelist(methods=["POST"])
def bill_to_client(version, rows, versions=None):
	"""A draft Variation Sales Order for client lines added after agreement."""
	from commercial_planning.services import revisions

	doc = _revision(version)
	order = revisions.bill_to_client(doc, parse_list(rows))
	return {"sales_order": order, "workspace": refreshed(doc.planning, versions)}
