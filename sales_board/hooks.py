app_name = "sales_board"
app_title = "Sales Board"
app_publisher = "Xlevel Retail Systems Ltd"
app_description = "Sales performance reporting for pay-on-delivery CRM"
app_email = "olamide@xlevelretail.com"
app_license = "mit"

before_install = "sales_board.install.before_install"
after_install = "sales_board.install.after_install"
after_migrate = "sales_board.install.after_migrate"

doc_events = {
	"CRM Order": {
		"validate": "sales_board.validations.crm_order_validate",
	}
}

scheduler_events = {
	"daily": ["sales_board.snapshot.daily"],
}
