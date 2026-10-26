import frappe


def execute():
	inspections = frappe.get_all(
		"Incoming Quality Inspection",
		filters={"revision_count": (">", 0)},
		pluck="name",
	)
	for inspection in inspections:
		entries = frappe.get_all(
			"Stock Entry",
			filters={
				"custom_incoming_quality_inspection": inspection,
				"docstatus": 1,
				"remarks": ("like", f"QC result revision for {inspection}:%"),
			},
			fields=["name", "custom_qc_result"],
			order_by="posting_date desc, posting_time desc, creation desc",
		)
		latest_by_result = {}
		for entry in entries:
			latest_by_result.setdefault(entry.custom_qc_result, entry.name)

		values = {}
		if latest_by_result.get("Accepted"):
			values["last_revision_accepted_stock_entry"] = latest_by_result["Accepted"]
		if latest_by_result.get("Rejected"):
			values["last_revision_rejected_stock_entry"] = latest_by_result["Rejected"]
		if values:
			frappe.db.set_value(
				"Incoming Quality Inspection",
				inspection,
				values,
				update_modified=False,
			)
