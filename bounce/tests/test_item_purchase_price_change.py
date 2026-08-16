from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from bounce.bounce_infinity.report.item_purchase_price_change.item_purchase_price_change import (
	_build_item_price_events,
	execute,
)


class TestItemPurchasePriceChange(UnitTestCase):
	def test_item_price_audit_uses_actual_change_date(self):
		item_price = frappe._dict(
			item_code="ITEM-1",
			item_name="Test Item",
			price=250,
			price_created_on="2026-08-13 09:00:00",
			modified="2026-08-16 19:30:00",
			creation="2026-08-13 09:00:00",
			currency="INR",
			uom="Nos",
			supplier="SUP-1",
			source_type="Buying Item Price",
			source_doctype="Item Price",
			source_document="ITEM-PRICE-1",
		)
		versions = [
			frappe._dict(
				docname="ITEM-PRICE-1",
				creation="2026-08-16 19:30:00",
				data=frappe.as_json({"changed": [["price_list_rate", 238.26, 250]]}),
			)
		]

		events = _build_item_price_events([item_price], versions)

		self.assertEqual(events[0].price, 238.26)
		self.assertEqual(str(events[0].effective_date), "2026-08-13")
		self.assertEqual(events[1].price, 250)
		self.assertEqual(str(events[1].effective_date), "2026-08-16")

	def test_latest_and_previous_prices_are_reported(self):
		events = [
			frappe._dict(
				item_code="ITEM-1",
				item_name="Test Item",
				price=100,
				effective_date="2026-08-01",
				creation="2026-08-01 10:00:00",
				currency="INR",
				uom="Nos",
				supplier="SUP-1",
				source_type="Purchase Receipt",
				source_doctype="Purchase Receipt",
				source_document="PR-1",
			),
			frappe._dict(
				item_code="ITEM-1",
				item_name="Test Item",
				price=110,
				effective_date="2026-08-14",
				creation="2026-08-14 10:00:00",
				currency="INR",
				uom="Nos",
				supplier="SUP-1",
				source_type="Purchase Receipt",
				source_doctype="Purchase Receipt",
				source_document="PR-2",
			),
		]
		with (
			patch(
				"bounce.bounce_infinity.report.item_purchase_price_change.item_purchase_price_change._get_purchase_receipt_prices",
				return_value=events,
			),
			patch(
				"bounce.bounce_infinity.report.item_purchase_price_change.item_purchase_price_change._get_buying_item_prices",
				return_value=[],
			),
		):
			_columns, data = execute()

		self.assertEqual(data[0].get("current_price"), 110)
		self.assertEqual(data[0].get("previous_price"), 100)
		self.assertEqual(data[0].get("effective_date"), "2026-08-14")
		self.assertEqual(data[0].get("change_percent"), 10)
