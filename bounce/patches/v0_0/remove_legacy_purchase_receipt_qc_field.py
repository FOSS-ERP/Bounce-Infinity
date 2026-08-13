import frappe


def execute():
	custom_field = "Purchase Receipt-custom_qc_done"
	if frappe.db.exists("Custom Field", custom_field):
		frappe.delete_doc("Custom Field", custom_field, ignore_permissions=True, force=True)
