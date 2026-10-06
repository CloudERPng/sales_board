frappe.query_reports["Sales Performance by Dimension"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "group_by", label: __("Group By"), fieldtype: "Select", reqd: 1, default: "Product", options: ["Product", "State", "Zone", "Branch", "Lead Channel", "Lead Source", "UTM Campaign", "CRM Status", "Order Date", "Order Week", "Weekday", "Hour of Day", "Online vs Manual", "Order Value Band", "Units per Order"] },
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "live", label: __("Live data (ignore month-end snapshot)"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		return data && data.bold ? `<b>${value}</b>` : value;
	},
};
