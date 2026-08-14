frappe.query_reports["Supplier Warranty Recovery"] = {
	filters: [
		{
			fieldname: "custom_supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
		},
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{
			fieldname: "custom_supplier_claim_status",
			label: __("Claim Status"),
			fieldtype: "Select",
			options: "\nNot Claimed\nPending\nClaimed\nAccepted\nRejected\nSettled",
		},
	],
};
