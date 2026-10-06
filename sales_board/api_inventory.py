"""Number cards for the Inventory Board (cached for 10 minutes)."""
import frappe
from frappe.utils import get_first_day, getdate, today

from sales_board.utils.data import check_access


def _company():
	return frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")


def _cached(name, fn):
	check_access()
	company = _company()
	key = f"sales_board:inv:{name}:{company}:{today()}"
	v = frappe.cache().get_value(key)
	if v is None:
		v = fn(company)
		frappe.cache().set_value(key, v, expires_in_sec=600)
	return v


def _stock(company):
	from sales_board.sales_board.report.stock_by_location.stock_by_location import build
	res = build(frappe._dict(company=company, as_of=today(), view_by="Location Type"))
	return {x["label"]: x["value"] for x in res["report_summary"]}


@frappe.whitelist()
def card_stock_value(filters=None):
	return {"value": _cached("stock", _stock)["Stock value"], "fieldtype": "Currency"}


@frappe.whitelist()
def card_agent_share(filters=None):
	return {"value": _cached("stock", _stock)["Held by agents"], "fieldtype": "Percent"}


@frappe.whitelist()
def card_stockout_locations(filters=None):
	def fn(company):
		from sales_board.sales_board.report.days_of_cover.days_of_cover import rows_for
		from sales_board.utils.data import settings
		rows, _d = rows_for(frappe._dict(company=company, as_of=today(), location_type="Agent"), settings())
		return len({r.warehouse for r in rows if r.status == "Stock-out"})
	return {"value": _cached("stockouts", fn), "fieldtype": "Int"}


@frappe.whitelist()
def card_lost_no_stock(filters=None):
	def fn(company):
		from sales_board.sales_board.report.lost_sales_from_stock_outs.lost_sales_from_stock_outs import build
		res = build(frappe._dict(company=company, from_date=get_first_day(getdate(today())), to_date=today(), view_by="Zone"))
		return res["report_summary"][1]["value"]
	return {"value": _cached("lost", fn), "fieldtype": "Currency"}


@frappe.whitelist()
def card_net_adjustments(filters=None):
	def fn(company):
		from sales_board.sales_board.report.inventory_adjustments.inventory_adjustments import build
		res = build(frappe._dict(company=company, from_date=get_first_day(getdate(today())), to_date=today(), view_by="Month"))
		return res["report_summary"][2]["value"]
	return {"value": _cached("adj", fn), "fieldtype": "Currency"}


@frappe.whitelist()
def card_idle_value(filters=None):
	def fn(company):
		from sales_board.sales_board.report.idle_stock.idle_stock import build
		res = build(frappe._dict(company=company, as_of=today()))
		return res["report_summary"][0]["value"]
	return {"value": _cached("idle", fn), "fieldtype": "Currency"}
