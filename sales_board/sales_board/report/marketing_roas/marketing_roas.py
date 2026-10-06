from frappe.utils import flt

from sales_board.utils.data import (_blank, aggregate, col, fetch_orders, fetch_spend, finish, marketer_name, mkey,
	pkey, settings, spend_kpis, spend_note, total_row)
from sales_board.utils.runner import run

REPORT = "Marketing ROAS"
FIELDS = ["marketer", "product", "spend", "orders", "valid", "delivered", "conversion", "cpl", "cpa",
	"delivered_value", "roas", "open", "open_value"]


def execute(filters=None):
	return run(REPORT, filters, build)


def build(f):
	f.branch = None
	s = settings()
	view = f.get("view_by") or "Marketer × Product"
	cohort, revenue = fetch_orders(f.company, f.from_date, f.to_date, None, s)
	spend = fetch_spend(f.from_date, f.to_date)

	def k(m, p):
		return (mkey(m) if view != "Product" else "", pkey(p) if view != "Marketer" else "")

	rows = aggregate(cohort, [], key=lambda r: k(r.marketer, r.requested_category),
		label=lambda r: (r.marketer_label, r.requested_category or "Not captured"))
	sp = {}
	for e in spend:
		kk = k(e.digital_marketer, e.product_category)
		sp[kk] = sp.get(kk, 0) + flt(e.amount_spent)
	names = {}
	for x in rows:
		x.spend = sp.pop(x.key, 0.0)
		finish(x, 0)
	for kk, amt in sp.items():  # spend that produced no leads in the period
		m, p = kk
		x = _blank(kk, (names.setdefault(m, marketer_name(m)) if m else "", p or "Not captured"))
		x.spend = amt
		rows.append(finish(x, 0))
	for x in rows:
		x.marketer, x.product = x.label if isinstance(x.label, tuple) else (x.label, "")
		if view == "Product":
			x.marketer = ""
		if view == "Marketer":
			x.product = ""
	rows.sort(key=lambda x: (-(x.spend or 0), -x.delivered_value))
	tot = total_row(rows, 0)
	tot.marketer, tot.product = "Total", ""
	rows.append(tot)
	data = [{k_: x.get(k_) for k_ in FIELDS + ["bold"]} for x in rows]
	columns = []
	if view != "Product":
		columns.append(col("Digital Marketer", "marketer", width=200))
	if view != "Marketer":
		columns.append(col("Product", "product", width=220))
	columns += [
		col("Ad Spend", "spend", "Currency", 130), col("Leads", "orders", "Int", 80), col("Valid Leads", "valid", "Int", 90),
		col("Delivered", "delivered", "Int", 85), col("Conversion %", "conversion", "Percent", 105),
		col("Cost per Valid Lead", "cpl", "Currency", 125), col("Cost per Delivered Order", "cpa", "Currency", 145),
		col("Delivered Value", "delivered_value", "Currency", 145), col("ROAS", "roas", "Float", 80),
		col("Still Open", "open", "Int", 85), col("Open Value", "open_value", "Currency", 130),
	]
	msg = ("Leads placed in the period against spend dated in the period. ROAS = delivered value ÷ spend; it rises as open "
		"orders convert. Rows with spend but no leads mean the product on the spend entry doesn't match any order "
		"in the period. " + spend_note(f))
	return {"columns": columns, "data": data, "report_summary": spend_kpis(cohort, spend), "message": msg}
