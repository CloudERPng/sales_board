frappe.query_reports["Lost Sales from Stock-outs"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "view_by", label: __("View By"), fieldtype: "Select", reqd: 1, default: "Zone", options: ["Zone", "State", "Product", "Delivery Agent"] },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "status" && data.status) {
			const c = { "Stock-out": "red", "Understocked": "orange", "Healthy": "green", "Overstocked": "yellow", "Idle": "gray", "Slow": "gray" }[data.status];
			if (c) value = `<span class="indicator-pill ${c}">${value}</span>`;
		}
		return data && data.bold ? `<b>${value}</b>` : value;
	},
};
