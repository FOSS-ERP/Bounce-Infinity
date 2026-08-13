from types import SimpleNamespace
from unittest.mock import patch

from frappe.tests import UnitTestCase

from bounce.bounce_infinity.doctype.incoming_quality_inspection.incoming_quality_inspection import (
	_get_pending_qty,
	_get_purchase_receipt_workflow_state,
	clear_qc_status_for_return,
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

	def test_purchase_receipt_workflow_state_tracks_qc_progress(self):
		self.assertEqual(_get_purchase_receipt_workflow_state("QC Pending"), "Approved")
		self.assertEqual(_get_purchase_receipt_workflow_state("Partial QC Done"), "Partial QC Done")
		self.assertEqual(_get_purchase_receipt_workflow_state("QC Completed"), "QC Completed")

	def test_return_purchase_receipt_has_no_qc_status(self):
		return_receipt = SimpleNamespace(is_return=1, custom_qc_status="QC Pending")

		clear_qc_status_for_return(return_receipt)

		self.assertEqual(return_receipt.custom_qc_status, "")
