from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from bounce.bounce_infinity.doctype.incoming_quality_inspection.incoming_quality_inspection import (
	_get_pending_qc_export_data,
	_get_pending_qty,
	_get_purchase_receipt_workflow_state,
	_validate_revision_quantities,
	clear_qc_status_for_return,
)


class TestIncomingQualityInspection(UnitTestCase):
	def test_qc_revision_preserves_inspected_total(self):
		allocation = SimpleNamespace(item_code="ITEM-1", accepted_qty=7, rejected_qty=3)

		_validate_revision_quantities(allocation, 8, 2)
		with self.assertRaises(frappe.ValidationError):
			_validate_revision_quantities(allocation, 8, 1)
		with self.assertRaises(frappe.ValidationError):
			_validate_revision_quantities(allocation, 11, -1)

	def test_pending_qc_export_contains_workbench_values(self):
		rows = [
			SimpleNamespace(
				item_code="ITEM-1",
				purchase_receipt="PR-1",
				supplier="SUP-1",
				posting_date="2026-08-16",
				source_warehouse="Quality - CO",
				received_qty=10,
				inspected_qty=4,
				pending_qty=6,
				qc_status="Partial QC Done",
				company="Test Company",
			)
		]

		data = _get_pending_qc_export_data(rows)

		self.assertEqual(data[1][0], "ITEM-1")
		self.assertEqual(data[1][1], "PR-1")
		self.assertEqual(data[1][7], 6)
		self.assertEqual(data[1][8], "Partial QC Done")

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
		self.assertEqual(
			_get_purchase_receipt_workflow_state("QC Completed - Fully Accepted"),
			"QC Completed - Fully Accepted",
		)
		self.assertEqual(
			_get_purchase_receipt_workflow_state("QC Completed - Partially Rejected"),
			"QC Completed - Partially Rejected",
		)

	def test_return_purchase_receipt_has_no_qc_status(self):
		return_receipt = SimpleNamespace(is_return=1, custom_qc_status="QC Pending")

		clear_qc_status_for_return(return_receipt)

		self.assertEqual(return_receipt.custom_qc_status, "")
