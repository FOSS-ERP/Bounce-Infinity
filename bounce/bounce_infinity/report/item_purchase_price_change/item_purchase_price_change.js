frappe.query_reports["Item Purchase Price Change"] = {
	filters: [
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
		},
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{
			fieldname: "source_type",
			label: __("Price Source"),
			fieldtype: "Select",
			options: "\nPurchase Receipt\nBuying Item Price",
		},
	],
};
