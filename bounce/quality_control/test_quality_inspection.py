from types import SimpleNamespace
from unittest.mock import patch

from frappe.tests import IntegrationTestCase

from bounce.quality_control.quality_inspection import _get_pending_qty


class TestQualityInspectionAllocation(IntegrationTestCase):
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
