"""Month-end snapshots: freeze each report for a closed month so reported numbers don't drift."""
import frappe
from frappe.utils import add_days, cint, get_first_day, getdate, now_datetime, today

from sales_board.utils.data import settings

DIMENSIONS = ["Product", "State", "Zone", "Branch", "Lead Channel", "Lead Source", "UTM Campaign", "Order Date",
	"Order Week", "Weekday", "Hour of Day", "Online vs Manual", "Order Value Band", "Units per Order"]
VIEWS = ["Closer", "Delivery Agent", "Marketer"]
BASE = "sales_board.sales_board.report"
REPORTS = [
	("Order Funnel", f"{BASE}.order_funnel.order_funnel.build", "", [""]),
	("Revenue Reconciliation", f"{BASE}.revenue_reconciliation.revenue_reconciliation.build", "", [""]),
	("Marketer Scorecard", f"{BASE}.marketer_scorecard.marketer_scorecard.build", "", [""]),
	("Closer Scorecard", f"{BASE}.closer_scorecard.closer_scorecard.build", "", [""]),
	("Delivery Agent Scorecard", f"{BASE}.delivery_agent_scorecard.delivery_agent_scorecard.build", "", [""]),
	("Sales Performance by Dimension", f"{BASE}.sales_performance_by_dimension.sales_performance_by_dimension.build",
		"group_by", DIMENSIONS),
	("Marketing ROAS", f"{BASE}.marketing_roas.marketing_roas.build", "view_by", ["Marketer × Product", "Product", "Marketer"]),
	("Pipeline Recovery", f"{BASE}.pipeline_recovery.pipeline_recovery.build", "view_by", VIEWS),
]


def daily():
	if not frappe.db.exists("DocType", "CRM Order"):
		return
	s = settings()
	if getdate(today()).day == cint(s.snapshot_day or 3):
		take_snapshots()
		if cint(s.get("pack_enabled")):
			from sales_board.pack import generate_month
			generate_month()


@frappe.whitelist()
def take_snapshots(period_end=None, overwrite=0):
	"""Freeze every report for the month ending period_end (default: last month).

	bench --site <site> execute sales_board.snapshot.take_snapshots --kwargs "{'period_end': '2026-09-30', 'overwrite': 1}"
	"""
	frappe.only_for(["Management", "System Manager"])
	end = getdate(period_end) if period_end else add_days(get_first_day(getdate(today())), -1)
	start = get_first_day(end)
	made = 0
	for company in frappe.get_all("Company", pluck="name"):
		if not frappe.db.count("CRM Order", {"company": company}):
			continue
		for report, path, key, variants in REPORTS:
			build = frappe.get_attr(path)
			for v in variants:
				filters = {"report_name": report, "company": company, "period_start": start, "period_end": end, "variant": v}
				existing = frappe.db.get_value("Sales Board Snapshot", filters)
				if existing and not cint(overwrite):
					continue
				f = frappe._dict(company=company, from_date=start, to_date=end)
				if key:
					f[key] = v
				res = build(f)
				if existing:
					frappe.delete_doc("Sales Board Snapshot", existing, ignore_permissions=True, force=True)
				frappe.get_doc({"doctype": "Sales Board Snapshot", **filters, "generated_on": now_datetime(),
					"result": frappe.as_json(res)}).insert(ignore_permissions=True)
				made += 1
	frappe.db.commit()
	return f"{made} snapshot(s) saved for {start} to {end}"
