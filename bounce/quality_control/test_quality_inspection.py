from types import SimpleNamespace
from unittest.mock import patch

from frappe.tests import IntegrationTestCase

from bounce.quality_control.quality_inspection import _aggregate_transfer_rows, _get_pending_qty


class TestQualityInspectionAllocation(IntegrationTestCase):
	def test_transfer_rows_are_grouped_by_item_and_source_warehouse(self):
		rows = [
			{"item_code": "ITEM-1", "source_warehouse": "Quality - C", "accepted_qty": 5},
			{"item_code": "ITEM-1", "source_warehouse": "Quality - C", "accepted_qty": 7},
			{"item_code": "ITEM-1", "source_warehouse": "Other Quality - C", "accepted_qty": 3},
		]

		self.assertEqual(
			_aggregate_transfer_rows(rows, "accepted_qty"),
			{("ITEM-1", "Quality - C"): 12, ("ITEM-1", "Other Quality - C"): 3},
		)

	@patch("bounce.quality_control.quality_inspection._get_inspected_qty")
	def test_pending_qty_subtracts_submitted_inspections(self, get_inspected_qty):
		get_inspected_qty.return_value = 35
		pr_item = SimpleNamespace(name="PRI-TEST", received_qty=100, qty=90)

		pending_qty = _get_pending_qty(pr_item)

		self.assertEqual(pending_qty, 65)
		get_inspected_qty.assert_called_once_with("PRI-TEST", None)

	@patch("bounce.quality_control.quality_inspection._get_inspected_qty")
	def test_pending_qty_never_becomes_negative(self, get_inspected_qty):
		get_inspected_qty.return_value = 110
		pr_item = SimpleNamespace(name="PRI-TEST", received_qty=100, qty=90)

		self.assertEqual(_get_pending_qty(pr_item), 0)

	@patch("bounce.quality_control.quality_inspection._get_inspected_qty")
	def test_pending_qty_falls_back_to_accepted_qty(self, get_inspected_qty):
		get_inspected_qty.return_value = 10
		pr_item = SimpleNamespace(name="PRI-TEST", received_qty=0, qty=50)

		self.assertEqual(_get_pending_qty(pr_item, "QI-TEST"), 40)
		get_inspected_qty.assert_called_once_with("PRI-TEST", "QI-TEST")
