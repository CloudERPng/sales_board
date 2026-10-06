"""Number card methods for the Sales Board workspace (month to date, cached for 10 minutes)."""
import frappe
from frappe.utils import add_days, get_first_day, getdate, today

from sales_board.utils.data import check_access, fetch_orders, fetch_spend, summary


def _mtd():
	check_access()
	company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
	key = f"sales_board:mtd:{company}:{today()}"
	cached = frappe.cache().get_value(key)
	if cached:
		return frappe._dict(cached)
	cohort, revenue = fetch_orders(company, get_first_day(getdate(today())), getdate(today()))
	s = summary(cohort, revenue)
	spend = sum(e.amount_spent or 0 for e in fetch_spend(get_first_day(getdate(today())), getdate(today())))
	s.roas = s.delivered_value / spend if spend else 0
	frappe.cache().set_value(key, dict(s), expires_in_sec=600)
	return s


@frappe.whitelist()
def card_revenue(filters=None):
	return {"value": _mtd().revenue, "fieldtype": "Currency"}


@frappe.whitelist()
def card_deliveries(filters=None):
	return {"value": _mtd().deliveries, "fieldtype": "Int"}


@frappe.whitelist()
def card_conversion(filters=None):
	return {"value": _mtd().conversion, "fieldtype": "Percent"}


@frappe.whitelist()
def card_success(filters=None):
	return {"value": _mtd().success, "fieldtype": "Percent"}


@frappe.whitelist()
def card_failed(filters=None):
	return {"value": _mtd().fail_rate, "fieldtype": "Percent"}


@frappe.whitelist()
def card_open_value(filters=None):
	return {"value": _mtd().open_value, "fieldtype": "Currency"}


@frappe.whitelist()
def card_unremitted(filters=None):
	"""Value of orders delivered in the last 60 days with no remitted or in-progress collection."""
	check_access()
	company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
	key = f"sales_board:unremitted:{company}:{today()}"
	v = frappe.cache().get_value(key)
	if v is None:
		_c, revenue = fetch_orders(company, add_days(getdate(today()), -60), getdate(today()))
		v = sum(r.order_total for r in revenue if r.coll_state == "Not collected")
		frappe.cache().set_value(key, v, expires_in_sec=600)
	return {"value": v, "fieldtype": "Currency"}


@frappe.whitelist()
def card_roas(filters=None):
	return {"value": _mtd().roas, "fieldtype": "Float"}
