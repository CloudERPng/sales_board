"""Shared inventory data layer for the Inventory Board.

Location types: HQ (listed in Sales Board Settings), Agent (the warehouse on an Agents record),
Transit (warehouse type Transit) and Other. Stock reconciliations are read from their own lines so a
quantity adjustment (stock found short or over) is kept apart from a revaluation (same qty, new cost).
"""
import frappe
from frappe.utils import add_days, cint, flt, getdate

from sales_board.utils.data import clean, settings, state_lookup

SALES_VOUCHERS = ("Sales Invoice", "Delivery Note", "POS Invoice")
PURCHASE_VOUCHERS = ("Purchase Receipt", "Purchase Invoice")
TRANSFER_PURPOSES = ("Material Transfer", "Material Transfer for Manufacture", "Send to Subcontractor")
LOCATION_TYPES = ["HQ", "Agent", "Transit", "Other"]
FLOW_FIELDS = ["purchased", "transfer_in", "customer_returns", "other_in", "opening_entry", "sold", "transfer_out",
	"other_out", "adj_qty"]


def lines(x):
	return [l.strip() for l in (x or "").splitlines() if l.strip()]


def locations(company, s=None):
	s = s or settings()
	hq = {r.warehouse for r in (s.get("hq_warehouses") or [])}
	resolve = state_lookup(s)
	agents = {}
	if frappe.db.exists("DocType", "Agents") and frappe.db.has_column("Agents", "warehouse"):
		for a in frappe.db.sql("""select name, full_name, warehouse, state, status, company from `tabAgents`
			where ifnull(warehouse, '') != ''""", as_dict=True):
			if not a.company or a.company == company:
				agents[a.warehouse] = a
	out = {}
	for w in frappe.db.sql("""select name, warehouse_name, warehouse_type from `tabWarehouse`
		where is_group = 0 and company = %s""", company, as_dict=True):
		a = agents.get(w.name)
		if w.name in hq:
			t = "HQ"
		elif a:
			t = "Agent"
		elif (w.warehouse_type or "") == "Transit":
			t = "Transit"
		else:
			t = "Other"
		st, zone = resolve(a.state) if a and a.state else ("", "")
		out[w.name] = frappe._dict(warehouse=w.name, type=t, agent=a.name if a else None,
			label=clean(a.full_name) if a and a.full_name else (w.warehouse_name or w.name),
			state=st, zone=zone, agent_status=a.status if a else "")
	return out


def location_of(locs, wh):
	return locs.get(wh) or frappe._dict(warehouse=wh, type="Other", label=wh, state="", zone="", agent=None,
		agent_status="")


def keep(loc, f):
	if f.get("location_type") and loc.type != f.location_type:
		return False
	if f.get("zone") and loc.zone != f.zone:
		return False
	if f.get("warehouse") and loc.warehouse != f.warehouse:
		return False
	return True


def balances(company, as_of):
	"""{(item, warehouse): {qty, value}} at the end of as_of (excludes cancelled entries)."""
	rows = frappe.db.sql("""select item_code, warehouse, qty_after_transaction as qty, stock_value as value from (
			select item_code, warehouse, qty_after_transaction, stock_value,
				row_number() over (partition by item_code, warehouse
					order by posting_date desc, posting_time desc, creation desc) as rn
			from `tabStock Ledger Entry`
			where is_cancelled = 0 and company = %(c)s and posting_date <= %(d)s) t
		where rn = 1""", {"c": company, "d": getdate(as_of)}, as_dict=True)
	return {(r.item_code, r.warehouse): frappe._dict(qty=flt(r.qty), value=flt(r.value)) for r in rows}


def blank_flow():
	return frappe._dict({k: 0.0 for k in FLOW_FIELDS + [f + "_value" for f in FLOW_FIELDS] + ["reval_value"]})


def adjustments(company, fd, td):
	"""Stock Reconciliation lines in the period with qty effect and revaluation split out."""
	rows = frappe.db.sql("""select sr.name as voucher, sr.posting_date, sr.owner, sr.purpose, sri.item_code,
			sri.warehouse, sri.qty, sri.current_qty, sri.valuation_rate, sri.current_valuation_rate,
			sri.amount, sri.current_amount
		from `tabStock Reconciliation Item` sri
		join `tabStock Reconciliation` sr on sr.name = sri.parent
		where sr.docstatus = 1 and sr.company = %(c)s and sr.posting_date between %(fd)s and %(td)s""",
		{"c": company, "fd": getdate(fd), "td": getdate(td)}, as_dict=True)
	for r in rows:
		r.dq = flt(r.qty) - flt(r.current_qty)
		rate = flt(r.current_valuation_rate) or flt(r.valuation_rate)
		r.qty_value = r.dq * rate
		r.total_value = flt(r.amount) - flt(r.current_amount)
		r.reval_value = r.total_value - r.qty_value
		r.is_opening = (r.purpose or "") == "Opening Stock"
		r.kind = ("Opening stock" if r.is_opening else "Shortage" if r.dq < 0 else "Excess found" if r.dq > 0
			else "Revaluation only")
	return rows


def movements(company, fd, td):
	"""{(item, warehouse): flows} for the period."""
	flows = {}
	rows = frappe.db.sql("""select sle.item_code, sle.warehouse, sle.voucher_type, ifnull(se.purpose, '') as purpose,
			sum(case when sle.actual_qty > 0 then sle.actual_qty else 0 end) as qty_in,
			sum(case when sle.actual_qty < 0 then -sle.actual_qty else 0 end) as qty_out,
			sum(case when sle.actual_qty > 0 then sle.stock_value_difference else 0 end) as val_in,
			sum(case when sle.actual_qty < 0 then -sle.stock_value_difference else 0 end) as val_out,
			sum(case when sle.actual_qty = 0 then sle.stock_value_difference else 0 end) as val_other
		from `tabStock Ledger Entry` sle
		left join `tabStock Entry` se on sle.voucher_type = 'Stock Entry' and se.name = sle.voucher_no
		where sle.is_cancelled = 0 and sle.company = %(c)s and sle.posting_date between %(fd)s and %(td)s
			and sle.voucher_type != 'Stock Reconciliation'
		group by sle.item_code, sle.warehouse, sle.voucher_type, se.purpose""",
		{"c": company, "fd": getdate(fd), "td": getdate(td)}, as_dict=True)
	for r in rows:
		f = flows.setdefault((r.item_code, r.warehouse), blank_flow())
		if r.voucher_type in SALES_VOUCHERS:
			i, o = "customer_returns", "sold"
		elif r.voucher_type in PURCHASE_VOUCHERS:
			i, o = "purchased", "other_out"
		elif r.voucher_type == "Stock Entry" and r.purpose in TRANSFER_PURPOSES:
			i, o = "transfer_in", "transfer_out"
		else:
			i, o = "other_in", "other_out"
		f[i] += flt(r.qty_in)
		f[i + "_value"] += flt(r.val_in)
		f[o] += flt(r.qty_out)
		f[o + "_value"] += flt(r.val_out)
		f.reval_value += flt(r.val_other)
	for a in adjustments(company, fd, td):
		f = flows.setdefault((a.item_code, a.warehouse), blank_flow())
		if a.is_opening:
			f.opening_entry += a.dq
			f.opening_entry_value += a.total_value
		else:
			f.adj_qty += a.dq
			f.adj_qty_value += a.qty_value
			f.reval_value += a.reval_value
	return flows


def sales_rate(company, as_of, days):
	"""{(item, warehouse): (units per day, cost per day)} over the `days` up to as_of, net of customer returns."""
	rows = frappe.db.sql("""select item_code, warehouse, sum(-actual_qty) as sold, sum(-stock_value_difference) as cost
		from `tabStock Ledger Entry`
		where is_cancelled = 0 and company = %(c)s and voucher_type in %(v)s
			and posting_date between %(fd)s and %(td)s
		group by item_code, warehouse""",
		{"c": company, "v": SALES_VOUCHERS, "fd": add_days(getdate(as_of), -(days - 1)), "td": getdate(as_of)},
		as_dict=True)
	return {(r.item_code, r.warehouse): (max(flt(r.sold), 0) / days, max(flt(r.cost), 0) / days) for r in rows}


def last_dates(company, as_of):
	rows = frappe.db.sql("""select item_code, warehouse,
			max(case when voucher_type in %(v)s and actual_qty < 0 then posting_date end) as last_sale,
			max(case when actual_qty > 0 then posting_date end) as last_receipt
		from `tabStock Ledger Entry`
		where is_cancelled = 0 and company = %(c)s and posting_date <= %(d)s
		group by item_code, warehouse""", {"c": company, "v": SALES_VOUCHERS, "d": getdate(as_of)}, as_dict=True)
	return {(r.item_code, r.warehouse): r for r in rows}


def item_names(codes):
	codes = list({c for c in codes if c})
	out = {}
	for i in range(0, len(codes), 1000):
		for r in frappe.get_all("Item", filters={"name": ["in", codes[i:i + 1000]]}, fields=["name", "item_name"]):
			out[r.name] = r.item_name or r.name
	return out


def cover_status(qty, daily, s, days_since_sale=None):
	under, over, idle = flt(s.understock_days or 5), flt(s.overstock_days or 45), cint(s.idle_days or 30)
	if qty <= 0:
		return ("Stock-out" if daily > 0 else "No stock"), (0 if daily > 0 else None)
	if daily <= 0:
		return ("Idle" if days_since_sale is None or days_since_sale > idle else "Slow"), None
	cover = qty / daily
	if cover < under:
		return "Understocked", cover
	if cover > over:
		return "Overstocked", cover
	return "Healthy", cover


def prepare(filters, need_period=True):
	from sales_board.utils.data import check_access
	check_access()
	f = frappe._dict(filters or {})
	if not f.company:
		f.company = frappe.defaults.get_user_default("Company")
	if not f.company:
		frappe.throw("Company is required.")
	if need_period:
		if not (f.from_date and f.to_date):
			frappe.throw("From Date and To Date are required.")
		if getdate(f.from_date) > getdate(f.to_date):
			frappe.throw("From Date cannot be after To Date.")
	elif not f.as_of:
		f.as_of = frappe.utils.today()
	return f


def ret(res):
	return res["columns"], res["data"], res.get("message"), res.get("chart"), res.get("report_summary")
