import json

import frappe
from frappe.utils import get_first_day, get_last_day, getdate, today

from sales_board.utils.data import check_access


def is_closed_month(f):
	fd, td = getdate(f.from_date), getdate(f.to_date)
	return fd == get_first_day(fd) and td == get_last_day(fd) and td < getdate(today())


def variant_of(f):
	return f.get("group_by") or f.get("view_by") or ""


def prepare(filters):
	f = frappe._dict(filters or {})
	if not f.company:
		f.company = frappe.defaults.get_user_default("Company")
	if not (f.company and f.from_date and f.to_date):
		frappe.throw("Company, From Date and To Date are required.")
	if getdate(f.from_date) > getdate(f.to_date):
		frappe.throw("From Date cannot be after To Date.")
	return f


def run(report_name, filters, build):
	"""Serve a frozen month-end snapshot for closed months (unless Live is ticked), else build live."""
	check_access()
	f = prepare(filters)
	if not f.get("live") and not f.get("branch") and is_closed_month(f):
		snap = frappe.db.get_value(
			"Sales Board Snapshot",
			{"report_name": report_name, "company": f.company, "period_start": getdate(f.from_date),
				"period_end": getdate(f.to_date), "variant": variant_of(f)},
			["result", "generated_on"], as_dict=True)
		if snap:
			r = json.loads(snap.result)
			msg = (f"Frozen month-end figures, captured {frappe.utils.format_datetime(snap.generated_on)}. "
				"Tick <b>Live data</b> to recalculate from current statuses.")
			return r["columns"], r["data"], msg, r.get("chart"), r.get("report_summary")
	res = build(f)
	return res["columns"], res["data"], res.get("message"), res.get("chart"), res.get("report_summary")
