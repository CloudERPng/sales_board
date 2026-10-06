import frappe
from frappe import _
from frappe.utils import cint

DESK_SAVE = "frappe.desk.form.save.savedocs"


def crm_order_validate(doc, method=None):
	"""Require a Failure Reason when a user moves an order to a failure status from the desk form.

	Only interactive desk saves are checked, so integrations, the agent portal and background jobs
	that set these statuses are never blocked.
	"""
	if frappe.form_dict.get("cmd") != DESK_SAVE:
		return
	if not frappe.db.exists("DocType", "Sales Board Settings"):
		return
	s = frappe.get_cached_doc("Sales Board Settings")
	if not cint(s.require_failure_reason):
		return
	statuses = [x.strip() for x in (s.failure_reason_statuses or "").splitlines() if x.strip()]
	if doc.status in statuses and doc.has_value_changed("status") and not doc.get("failure_reason"):
		frappe.throw(
			_("Select a Failure Reason before marking this order {0}.").format(doc.status),
			title=_("Failure Reason required"),
		)
