from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	events = _get_purchase_receipt_prices(filters) + _get_buying_item_prices(filters)
	grouped = defaultdict(list)
	for event in events:
		key = (
			event.item_code,
			event.get("warehouse") or "",
			event.get("price_list") or "",
			event.get("uom") or "",
			event.get("supplier") or "",
		)
		grouped[key].append(event)

	data = []
	for group_key, item_events in grouped.items():
		item_events.sort(key=lambda row: (row.effective_date, row.creation), reverse=True)
		current = item_events[0]
		previous = item_events[1] if len(item_events) > 1 else frappe._dict()
		previous_price = flt(previous.get("price"))
		change_amount = flt(current.price) - previous_price if previous else 0
		data.append(
			{
				"item_code": group_key[0],
				"item_name": current.item_name,
				"warehouse": current.get("warehouse"),
				"price_list": current.get("price_list"),
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

	data.sort(key=lambda row: (row["item_code"], row.get("warehouse") or ""))
	return _columns(), data


def _get_purchase_receipt_prices(filters):
	rows = frappe.db.sql(
		"""
		SELECT pri.item_code, pri.item_name, pri.rate price, pri.uom,
			pri.warehouse, pr.buying_price_list price_list,
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
		and (not filters.warehouse or row.warehouse == filters.warehouse)
		and (not filters.company or row.company == filters.company)
		and (not filters.source_type or row.source_type == filters.source_type)
	]


def _get_buying_item_prices(filters):
	if filters.source_type == "Purchase Receipt":
		return []
	rows = frappe.db.sql(
		"""
		SELECT price.item_code, item.item_name, price.price_list_rate price,
			price.uom, price.currency, price.supplier, price.price_list,
			price.custom_warehouse warehouse, warehouse.company,
			price.creation price_created_on, price.modified,
			price.creation, 'Buying Item Price' source_type,
			'Item Price' source_doctype,
			price.name source_document
		FROM `tabItem Price` price
		INNER JOIN `tabItem` item ON item.name = price.item_code
		LEFT JOIN `tabWarehouse` warehouse ON warehouse.name = price.custom_warehouse
		WHERE price.buying = 1 AND price.price_list_rate IS NOT NULL
		ORDER BY price.modified DESC
		""",
		as_dict=True,
	)
	rows = [
		row
		for row in rows
		if (not filters.item_code or row.item_code == filters.item_code)
		and (not filters.warehouse or row.warehouse == filters.warehouse)
		and (not filters.company or row.company == filters.company)
	]
	if not rows:
		return []

	versions = frappe.get_all(
		"Version",
		filters={
			"ref_doctype": "Item Price",
			"docname": ("in", [row.source_document for row in rows]),
		},
		fields=["docname", "creation", "data"],
		order_by="creation asc",
	)
	return _build_item_price_events(rows, versions)


def _build_item_price_events(rows: list, versions: list) -> list:
	versions_by_document = defaultdict(list)
	for version in versions:
		data = frappe.parse_json(version.data) or {}
		for change in data.get("changed", []):
			if len(change) >= 3 and change[0] == "price_list_rate":
				versions_by_document[version.docname].append(
					frappe._dict(creation=version.creation, old_price=change[1], new_price=change[2])
				)

	events = []
	for row in rows:
		changes = versions_by_document[row.source_document]
		initial_price = changes[0].old_price if changes else row.price
		events.append(_make_item_price_event(row, initial_price, row.price_created_on))
		for change in changes:
			events.append(_make_item_price_event(row, change.new_price, change.creation))

		if changes and flt(changes[-1].new_price) != flt(row.price):
			# Version history can be pruned; keep the current master value visible.
			events.append(_make_item_price_event(row, row.price, row.modified))

	return events


def _make_item_price_event(row: frappe._dict, price: float, changed_on) -> frappe._dict:
	event = frappe._dict(row.copy())
	event.price = flt(price)
	event.effective_date = getdate(changed_on)
	event.creation = get_datetime(changed_on)
	return event


def _columns():
	return [
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 160},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 200},
		{
			"fieldname": "warehouse",
			"label": _("Warehouse"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 210,
		},
		{
			"fieldname": "price_list",
			"label": _("Price List"),
			"fieldtype": "Link",
			"options": "Price List",
			"width": 130,
		},
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
