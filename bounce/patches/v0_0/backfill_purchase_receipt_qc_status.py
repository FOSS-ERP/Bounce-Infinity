import frappe


def execute():
	frappe.db.sql(
		"""
		UPDATE `tabPurchase Receipt`
		SET custom_qc_status = 'QC Pending'
		WHERE docstatus = 1
			AND COALESCE(custom_qc_status, '') NOT IN ('QC Pending', 'Partial QC Done', 'QC Completed')
		"""
	)
