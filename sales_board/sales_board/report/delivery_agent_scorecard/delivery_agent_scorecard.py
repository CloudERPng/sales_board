from frappe.utils import cint

from sales_board.utils.data import col, aggregate, fetch_orders, kpis, rank, settings, summary, total_row
from sales_board.utils.runner import run

REPORT = "Delivery Agent Scorecard"
FIELDS = ["label", "main_attr", "dispatched", "delivered", "success", "failed", "fail_rate", "stalled", "transit",
	"open_value", "deliveries", "gross", "fees", "discount", "other_exp", "net_cash", "net_collected",
	"outstanding_value", "fee_actual_pct", "avg_days", "avg_remit_days", "rank"]


def execute(filters=None):
	return run(REPORT, filters, build)


def build(f):
	s = settings()
	cohort, revenue = fetch_orders(f.company, f.from_date, f.to_date, f.branch, s)
	dispatched = [r for r in cohort if r.dispatched and r.valid]
	rows = aggregate(dispatched, revenue, key=lambda r: r.agent, label=lambda r: r.agent_label,
		attr=lambda r: r.state_clean)
	rank(rows, "dispatched", cint(s.min_agent_orders), "success")
	rows.sort(key=lambda x: -x.gross)
	rows.append(total_row(rows, sum(r.rev_value for r in revenue)))
	data = [{k: x.get(k) for k in FIELDS + ["bold"]} for x in rows]
	columns = [
		col("Delivery Agent", "label", width=230), col("Main State", "main_attr", width=130),
		col("Dispatched", "dispatched", "Int", 90), col("Delivered", "delivered", "Int", 85),
		col("Success %", "success", "Percent", 90), col("Failed at Door", "failed", "Int", 100),
		col("Failed %", "fail_rate", "Percent", 85), col("Stalled", "stalled", "Int", 75),
		col("In Transit", "transit", "Int", 80), col("Value Still with Agent", "open_value", "Currency", 150),
		col("Deliveries in Period", "deliveries", "Int", 120), col("Order Value Delivered", "gross", "Currency", 150),
		col("Delivery Fees", "fees", "Currency", 120), col("Discounts", "discount", "Currency", 110),
		col("Other Expenses", "other_exp", "Currency", 115), col("Net Cash Due", "net_cash", "Currency", 140),
		col("Net Remitted", "net_collected", "Currency", 140), col("Not Yet Remitted", "outstanding_value", "Currency", 140),
		col("Fees from Collections %", "fee_actual_pct", "Percent", 140),
		col("Avg Days Assignment → Delivery", "avg_days", "Float", 150),
		col("Avg Days Delivery → Remittance", "avg_remit_days", "Float", 150),
		col("Rank (Success %)", "rank", "Int", 110),
	]
	return {"columns": columns, "data": data, "report_summary": kpis(summary(cohort, revenue)),
		"message": "Fees, discounts and other expenses are actuals from Agent Collections. Where no collection exists yet, "
			"the fee falls back to the order's Agent Delivery Fee or the default (see 'Fees from Collections %'). "
			"Not Yet Remitted = delivered orders with no remitted or in-progress collection."}
