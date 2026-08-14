import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	data = frappe.db.sql(
		"""
		SELECT serial.name serial_no, serial.item_code, serial.customer,
			claim.name warranty_claim, serial.warranty_expiry_date,
			serial.custom_supplier supplier,
			serial.custom_original_purchase_receipt original_purchase_receipt,
			serial.custom_original_purchase_rate original_purchase_rate,
			serial.custom_supplier_claim_multiplier claim_multiplier,
			serial.custom_supplier_claim_amount claim_amount,
			serial.custom_purchase_return purchase_return,
			serial.custom_supplier_debit_note debit_note,
			serial.custom_supplier_claim_status claim_status,
			serial.custom_supplier_claim_date claim_date,
			debit.posting_date settlement_date
		FROM `tabSerial No` serial
		LEFT JOIN `tabWarranty Claim` claim ON claim.serial_no = serial.name AND claim.docstatus < 2
		LEFT JOIN `tabPurchase Invoice` debit ON debit.name = serial.custom_supplier_debit_note
		WHERE serial.custom_original_purchase_receipt IS NOT NULL
		ORDER BY serial.modified DESC
		""",
		as_dict=True,
	)
	field_map = {
		"custom_supplier": "supplier",
		"custom_supplier_claim_status": "claim_status",
		"item_code": "item_code",
	}
	data = [
		row
		for row in data
		if all(
			not filters.get(source) or row.get(target) == filters[source]
			for source, target in field_map.items()
		)
	]
	return _columns(), data


def _columns():
	return [
		{
			"fieldname": "serial_no",
			"label": _("Serial No"),
			"fieldtype": "Link",
			"options": "Serial No",
			"width": 160,
		},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 160},
		{
			"fieldname": "customer",
			"label": _("Customer"),
			"fieldtype": "Link",
			"options": "Customer",
			"width": 160,
		},
		{
			"fieldname": "warranty_claim",
			"label": _("Warranty Claim"),
			"fieldtype": "Link",
			"options": "Warranty Claim",
			"width": 160,
		},
		{
			"fieldname": "warranty_expiry_date",
			"label": _("Warranty Expiry"),
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"fieldname": "supplier",
			"label": _("Supplier"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 170,
		},
		{
			"fieldname": "original_purchase_receipt",
			"label": _("Original Purchase Receipt"),
			"fieldtype": "Link",
			"options": "Purchase Receipt",
			"width": 180,
		},
		{
			"fieldname": "original_purchase_rate",
			"label": _("Original Purchase Rate"),
			"fieldtype": "Currency",
			"width": 140,
		},
		{"fieldname": "claim_multiplier", "label": _("Claim Multiplier"), "fieldtype": "Float", "width": 120},
		{"fieldname": "claim_amount", "label": _("Claim Amount"), "fieldtype": "Currency", "width": 130},
		{
			"fieldname": "purchase_return",
			"label": _("Purchase Return"),
			"fieldtype": "Link",
			"options": "Purchase Receipt",
			"width": 160,
		},
		{
			"fieldname": "debit_note",
			"label": _("Debit Note"),
			"fieldtype": "Link",
			"options": "Purchase Invoice",
			"width": 160,
		},
		{"fieldname": "claim_status", "label": _("Claim Status"), "fieldtype": "Data", "width": 110},
		{"fieldname": "claim_date", "label": _("Claim Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "settlement_date", "label": _("Settlement Date"), "fieldtype": "Date", "width": 120},
	]
