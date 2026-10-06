# Default configuration loaded into Sales Board Settings on install. All of it is editable afterwards.

STATUS_MAP = {
	"Won": ["Delivered"],
	"Reversed": ["Delivered Order Cancelled", "Returned"],
	"Invalid": ["Duplicate"],
	"Lost": ["Cancelled", "Rejected", "No Product", "No Stock", "Failed"],
	"Transit": ["Dispatch Assigned", "Processing", "Order Accepted", "Agent Notified", "Delivery In Progress", "Delivery Rescheduled"],
	"Open": ["New Lead", "Qualified", "Confirmed", "Assigned", "On Hold", "Not Picking", "Call Back", "Not Reachable",
		"Agent Unavailable", "Not ready", "Switched Off", "Rescheduled"],
}

ZONES = {
	"North Central": ["Benue", "Kogi", "Kwara", "Nasarawa", "Niger", "Plateau", "Federal Capital Territory"],
	"North East": ["Adamawa", "Bauchi", "Borno", "Gombe", "Taraba", "Yobe"],
	"North West": ["Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Sokoto", "Zamfara"],
	"South East": ["Abia", "Anambra", "Ebonyi", "Enugu", "Imo"],
	"South South": ["Akwa Ibom", "Bayelsa", "Cross River", "Delta", "Edo", "Rivers"],
	"South West": ["Ekiti", "Lagos", "Ogun", "Ondo", "Osun", "Oyo"],
}

STATE_ALIASES = {
	"Abuja": "Federal Capital Territory", "FCT": "Federal Capital Territory", "F.C.T": "Federal Capital Territory",
	"FCT Abuja": "Federal Capital Territory", "Abuja FCT": "Federal Capital Territory",
	"Akwa-Ibom": "Akwa Ibom", "Awka Ibom": "Akwa Ibom", "Akwaibom": "Akwa Ibom",
	"Bayesla": "Bayelsa", "Beyelsa": "Bayelsa", "Bornu": "Borno",
	"Cross Rivers": "Cross River", "Crossriver": "Cross River", "Calabar": "Cross River",
	"Nassarawa": "Nasarawa", "Nassrawa": "Nasarawa", "Rives": "Rivers", "Port Harcourt": "Rivers",
	"Zafara": "Zamfara", "Anambara": "Anambra", "Enegu": "Enugu", "Ibadan": "Oyo", "Kastina": "Katsina",
}

FAILURE_REASON_STATUSES = "Cancelled\nRejected"
