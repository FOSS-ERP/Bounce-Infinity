import frappe


def execute():
	for custom_field in (
		"Quality Inspection-custom_qc_item",
		"Quality Inspection-custom_qc_receipts",
		"Quality Inspection-custom_accepted_stock_entry",
		"Quality Inspection-custom_rejected_stock_entry",
	):
		if frappe.db.exists("Custom Field", custom_field):
			frappe.delete_doc("Custom Field", custom_field, ignore_permissions=True, force=True)

	if frappe.db.exists("DocType", "Bounce QC Settings"):
		frappe.delete_doc("DocType", "Bounce QC Settings", ignore_permissions=True, force=True)

	if frappe.db.exists("DocType", "Quality Inspection PR Detail"):
		if not frappe.db.count("Quality Inspection PR Detail"):
			frappe.delete_doc("DocType", "Quality Inspection PR Detail", ignore_permissions=True, force=True)
