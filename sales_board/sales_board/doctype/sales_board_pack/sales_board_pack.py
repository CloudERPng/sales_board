import frappe
from frappe.model.document import Document


class SalesBoardPack(Document):
	@frappe.whitelist()
	def regenerate(self):
		from sales_board.pack import attach_pack
		attach_pack(self)
		return self.pack_file

	@frappe.whitelist()
	def send_to_management(self):
		from sales_board.pack import send_pack
		return send_pack(self)
