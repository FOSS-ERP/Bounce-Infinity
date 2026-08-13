import frappe


def execute():
	for custom_field in (
		"Warehouse-custom_qc_accepted_warehouse",
		"Warehouse-custom_qc_rejected_warehouse",
	):
		if frappe.db.exists("Custom Field", custom_field):
			frappe.delete_doc("Custom Field", custom_field, ignore_permissions=True, force=True)
