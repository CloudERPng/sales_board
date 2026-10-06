import json

import frappe
from frappe.permissions import add_permission, update_permission_property

from sales_board.utils.defaults import FAILURE_REASON_STATUSES, STATE_ALIASES, STATUS_MAP, ZONES

ROLE = "Management"
MODULE = "Sales Board"
CARDS = [
	("Revenue MTD", "sales_board.api.card_revenue", "#1F5F3F"),
	("Deliveries MTD", "sales_board.api.card_deliveries", "#2E8B6E"),
	("Conversion MTD", "sales_board.api.card_conversion", "#E9A23B"),
	("Delivery Success MTD", "sales_board.api.card_success", "#2E8B6E"),
	("Failed After Dispatch MTD", "sales_board.api.card_failed", "#C0392B"),
	("Open Pipeline MTD", "sales_board.api.card_open_value", "#E07A5F"),
	("Cash Not Yet Remitted", "sales_board.api.card_unremitted", "#C0392B"),
	("ROAS MTD", "sales_board.api.card_roas", "#E9A23B"),
]
INV_CARDS = [
	("Stock Value", "sales_board.api_inventory.card_stock_value", "#1F5F3F"),
	("Stock Held by Agents %", "sales_board.api_inventory.card_agent_share", "#E9A23B"),
	("Locations with Stock-outs", "sales_board.api_inventory.card_stockout_locations", "#C0392B"),
	("Lost to No Stock MTD", "sales_board.api_inventory.card_lost_no_stock", "#C0392B"),
	("Net Stock Adjustments MTD", "sales_board.api_inventory.card_net_adjustments", "#E07A5F"),
	("Idle Stock Value", "sales_board.api_inventory.card_idle_value", "#E07A5F"),
]
INV_GROUPS = [
	("Stock position", ["Stock by Location", "Days of Cover", "Idle Stock"]),
	("Movement and efficiency", ["Agent Stock Statement", "Distribution Efficiency", "Stock Transfers",
		"Lost Sales from Stock-outs"]),
	("Control", ["Inventory Adjustments"]),
]
REPORT_GROUPS = [
	("Company", ["Order Funnel", "Revenue Reconciliation", "Pipeline Recovery", "Sales Performance by Dimension", "Marketing ROAS"]),
	("Stakeholders", ["Marketer Scorecard", "Closer Scorecard", "Delivery Agent Scorecard", "Agent Remittance"]),
	("Monthly pack", [("DocType", "Sales Board Pack", 0)]),
]


def before_install():
	ensure_role()


def after_install():
	after_migrate()


def after_migrate():
	ensure_role()
	ensure_settings()
	ensure_crm_permission()
	ensure_number_cards()
	ensure_workspace()
	ensure_workspace("Inventory Board", INV_CARDS, INV_GROUPS, "Today", "stock", 31)


def ensure_role():
	if not frappe.db.exists("Role", ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert(ignore_permissions=True)


def ensure_settings():
	s = frappe.get_single("Sales Board Settings")
	first_time = not s.status_map
	if first_time:
		s.default_agent_fee = 5000
		s.cost_of_sales_pct = 10
		s.min_closer_orders = 100
		s.min_agent_orders = 50
		s.min_marketer_leads = 100
		s.require_failure_reason = 1
		s.failure_reason_statuses = FAILURE_REASON_STATUSES
		s.snapshot_day = 3
		for stype, statuses in STATUS_MAP.items():
			for st in statuses:
				s.append("status_map", {"crm_status": st, "status_type": stype})
		for zone, states in ZONES.items():
			for st in states:
				s.append("states", {"state": st, "zone": zone})
		for alias, st in STATE_ALIASES.items():
			s.append("state_aliases", {"alias": alias, "state": st})
	if not frappe.db.sql("select 1 from `tabSingles` where doctype = 'Sales Board Settings' and field = 'pack_enabled'"):
		s.pack_enabled = 1
	if not s.get("understock_days"):
		s.understock_days = 5
		s.overstock_days = 45
		s.idle_days = 30
		s.cover_lookback_days = 30
		s.large_adjustment_value = 100000
		s.no_stock_statuses = "No Product\nNo Stock"
	if not s.remitted_statuses:
		s.remitted_statuses = "Completed"
		s.in_progress_statuses = "Pending\nAwaiting Payment"
		s.review_statuses = "Needs Review"
		s.revenue_net_of_discounts = 1
	# Any CRM Order status not yet mapped is added as Open so it shows up for review
	if frappe.db.exists("DocType", "CRM Order"):
		meta = frappe.get_meta("CRM Order")
		df = meta.get_field("status")
		mapped = {r.crm_status for r in s.status_map}
		for st in (df.options or "").splitlines() if df else []:
			if st.strip() and st.strip() not in mapped:
				s.append("status_map", {"crm_status": st.strip(), "status_type": "Open"})
	s.flags.ignore_permissions = True
	s.flags.ignore_mandatory = True
	s.save()


def ensure_crm_permission():
	"""Management needs read + report on CRM Order to run the reports."""
	if not frappe.db.exists("DocType", "CRM Order"):
		return
	if not frappe.db.exists("Custom DocPerm", {"parent": "CRM Order", "role": ROLE, "permlevel": 0}):
		add_permission("CRM Order", ROLE, 0)
	for ptype in ("read", "report", "export", "print"):
		update_permission_property("CRM Order", ROLE, 0, ptype, 1, validate=False)


def ensure_number_cards():
	for label, method, color in CARDS + INV_CARDS:
		if frappe.db.exists("Number Card", label):
			continue
		frappe.get_doc({"doctype": "Number Card", "name": label, "label": label, "type": "Custom", "method": method,
			"is_public": 1, "is_standard": 0, "module": MODULE, "color": color,
			"show_percentage_stats": 0}).insert(ignore_permissions=True)


def ensure_workspace(name="Sales Board", cards=None, groups=None, heading="This month to date", icon="income", seq=30):
	cards = CARDS if cards is None else cards
	groups = REPORT_GROUPS if groups is None else groups
	if frappe.db.exists("Workspace", name):
		return update_workspace(name, cards, groups)
	blocks = [{"id": "sbh1", "type": "header", "data": {"text": f"<span class=\"h4\"><b>{heading}</b></span>", "col": 12}}]
	for i, (label, _m, _c) in enumerate(cards):
		blocks.append({"id": f"sbn{i}", "type": "number_card", "data": {"number_card_name": label, "col": 4}})
	blocks.append({"id": "sbsp", "type": "spacer", "data": {"col": 12}})
	blocks.append({"id": "sbh2", "type": "header", "data": {"text": "<span class=\"h4\"><b>Reports</b></span>", "col": 12}})
	links = []
	for i, (card, reports) in enumerate(groups + [("Setup", [])]):
		blocks.append({"id": f"sbc{i}", "type": "card", "data": {"card_name": card, "col": 4}})
		items = [("Report", r, 1) if isinstance(r, str) else tuple(r) for r in reports] if reports else [
			("DocType", "Sales Board Settings", 0), ("DocType", "Sales Board Snapshot", 0)]
		links.append({"type": "Card Break", "label": card, "link_count": len(items), "hidden": 0, "onboard": 0})
		for link_type, link_name, is_qr in items:
			links.append({"type": "Link", "label": link_name, "link_type": link_type, "link_to": link_name,
				"is_query_report": is_qr, "hidden": 0, "onboard": 0, "link_count": 0})
	frappe.get_doc({
		"doctype": "Workspace", "name": name, "label": name, "title": name,
		"module": MODULE, "public": 1, "icon": icon, "sequence_id": seq, "content": json.dumps(blocks),
		"number_cards": [{"number_card_name": label, "label": label} for label, _m, _c in cards],
		"links": links, "roles": [{"role": ROLE}, {"role": "System Manager"}],
	}).insert(ignore_permissions=True)


def update_workspace(name="Sales Board", cards=None, groups=None):
	"""Add any new cards or reports to an existing workspace without disturbing edits made to it."""
	cards = CARDS if cards is None else cards
	groups = REPORT_GROUPS if groups is None else groups
	ws = frappe.get_doc("Workspace", name)
	blocks = json.loads(ws.content or "[]")
	have_cards = {b["data"].get("number_card_name") for b in blocks if b.get("type") == "number_card"}
	last_card = max([i for i, b in enumerate(blocks) if b.get("type") == "number_card"] or [0])
	changed = False
	for label, _m, _c in cards:
		if label not in have_cards:
			last_card += 1
			blocks.insert(last_card, {"id": frappe.generate_hash(length=10), "type": "number_card",
				"data": {"number_card_name": label, "col": 4}})
			ws.append("number_cards", {"number_card_name": label, "label": label})
			changed = True
	have_links = {l.link_to for l in ws.links if l.type == "Link"}
	for card, reports in groups:
		missing = [("Report", r, 1) if isinstance(r, str) else tuple(r) for r in reports]
		missing = [m for m in missing if m[1] not in have_links]
		if not missing:
			continue
		links = [l.as_dict() for l in ws.links]
		new = [{"type": "Link", "label": n, "link_type": t, "link_to": n, "is_query_report": q,
			"hidden": 0, "onboard": 0, "link_count": 0} for t, n, q in missing]
		idx = next((i for i, l in enumerate(links) if l["type"] == "Card Break" and l["label"] == card), None)
		if idx is None:
			links.append({"type": "Card Break", "label": card, "link_count": len(new), "hidden": 0, "onboard": 0})
			links.extend(new)
			blocks.append({"id": frappe.generate_hash(length=10), "type": "card", "data": {"card_name": card, "col": 4}})
		else:
			end = idx + 1
			while end < len(links) and links[end]["type"] == "Link":
				end += 1
			links[end:end] = new
			links[idx]["link_count"] = (links[idx].get("link_count") or 0) + len(new)
		ws.set("links", [])
		for l in links:
			for k in ("name", "parent", "parentfield", "parenttype", "idx", "creation", "modified", "owner", "modified_by", "docstatus"):
				l.pop(k, None)
			ws.append("links", l)
		changed = True
	if changed:
		ws.content = json.dumps(blocks)
		ws.save(ignore_permissions=True)
