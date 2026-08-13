from types import SimpleNamespace
from unittest.mock import patch

from frappe.tests import UnitTestCase

from bounce.bounce_infinity.doctype.incoming_quality_inspection.incoming_quality_inspection import (
	_get_pending_qty,
)


class TestIncomingQualityInspection(UnitTestCase):
	@patch(
		"bounce.bounce_infinity.doctype.incoming_quality_inspection.incoming_quality_inspection._get_inspected_qty"
	)
	def test_pending_qty_subtracts_submitted_qc(self, get_inspected_qty):
		get_inspected_qty.return_value = 35
		row = SimpleNamespace(name="PRI-TEST", received_qty=100)

		self.assertEqual(_get_pending_qty(row), 65)

	@patch(
		"bounce.bounce_infinity.doctype.incoming_quality_inspection.incoming_quality_inspection._get_inspected_qty"
	)
	def test_pending_qty_never_becomes_negative(self, get_inspected_qty):
		get_inspected_qty.return_value = 110
		row = SimpleNamespace(name="PRI-TEST", received_qty=100)

		self.assertEqual(_get_pending_qty(row), 0)
