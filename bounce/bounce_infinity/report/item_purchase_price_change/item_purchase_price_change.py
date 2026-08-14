from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	events = _get_purchase_receipt_prices(filters) + _get_buying_item_prices(filters)
	grouped = defaultdict(list)
	for event in events:
		grouped[event.item_code].append(event)

	data = []
	for item_code, item_events in grouped.items():
		item_events.sort(key=lambda row: (row.effective_date, row.creation), reverse=True)
		current = item_events[0]
		previous = item_events[1] if len(item_events) > 1 else frappe._dict()
		previous_price = flt(previous.get("price"))
		change_amount = flt(current.price) - previous_price if previous else 0
		data.append(
			{
				"item_code": item_code,
				"item_name": current.item_name,
				"current_price": current.price,
				"previous_price": previous.get("price"),
				"change_amount": change_amount if previous else None,
				"change_percent": (change_amount / previous_price * 100) if previous_price else None,
				"effective_date": current.effective_date,
				"previous_effective_date": previous.get("effective_date"),
				"currency": current.currency,
				"uom": current.uom,
				"supplier": current.supplier,
				"source_type": current.source_type,
				"source_doctype": current.source_doctype,
				"source_document": current.source_document,
			}
		)

	data.sort(key=lambda row: row["item_code"])
	return _columns(), data


def _get_purchase_receipt_prices(filters):
	rows = frappe.db.sql(
		"""
		SELECT pri.item_code, pri.item_name, pri.rate price, pri.uom,
			pr.currency, pr.supplier, pr.posting_date effective_date,
			pr.creation, 'Purchase Receipt' source_type,
			'Purchase Receipt' source_doctype,
			pr.name source_document, pr.company
		FROM `tabPurchase Receipt Item` pri
		INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
		WHERE pr.docstatus = 1 AND pr.is_return = 0 AND pri.rate IS NOT NULL
		ORDER BY pr.posting_date DESC, pr.creation DESC
		""",
		as_dict=True,
	)
	return [
		row
		for row in rows
		if (not filters.item_code or row.item_code == filters.item_code)
		and (not filters.company or row.company == filters.company)
		and (not filters.source_type or row.source_type == filters.source_type)
	]


def _get_buying_item_prices(filters):
	if filters.company or filters.source_type == "Purchase Receipt":
		return []
	rows = frappe.db.sql(
		"""
		SELECT price.item_code, item.item_name, price.price_list_rate price,
			price.uom, price.currency, price.supplier,
			COALESCE(price.valid_from, DATE(price.creation)) effective_date,
			price.creation, 'Buying Item Price' source_type,
			'Item Price' source_doctype,
			price.name source_document
		FROM `tabItem Price` price
		INNER JOIN `tabItem` item ON item.name = price.item_code
		WHERE price.buying = 1 AND price.price_list_rate IS NOT NULL
		ORDER BY effective_date DESC, price.creation DESC
		""",
		as_dict=True,
	)
	return [row for row in rows if not filters.item_code or row.item_code == filters.item_code]


def _columns():
	return [
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 160},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 200},
		{
			"fieldname": "current_price",
			"label": _("Current Price"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{
			"fieldname": "previous_price",
			"label": _("Previous Price"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{
			"fieldname": "change_amount",
			"label": _("Price Change"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 115,
		},
		{"fieldname": "change_percent", "label": _("Change %"), "fieldtype": "Percent", "width": 100},
		{"fieldname": "effective_date", "label": _("Effective From"), "fieldtype": "Date", "width": 115},
		{
			"fieldname": "previous_effective_date",
			"label": _("Previous Effective From"),
			"fieldtype": "Date",
			"width": 150,
		},
		{
			"fieldname": "currency",
			"label": _("Currency"),
			"fieldtype": "Link",
			"options": "Currency",
			"width": 90,
		},
		{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM", "width": 80},
		{
			"fieldname": "supplier",
			"label": _("Latest Supplier"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 170,
		},
		{"fieldname": "source_type", "label": _("Current Price Source"), "fieldtype": "Data", "width": 145},
		{"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "hidden": 1},
		{
			"fieldname": "source_document",
			"label": _("Source Document"),
			"fieldtype": "Dynamic Link",
			"options": "source_doctype",
			"width": 170,
		},
	]
