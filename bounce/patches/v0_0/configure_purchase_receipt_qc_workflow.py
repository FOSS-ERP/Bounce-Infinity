import frappe

WORKFLOW_NAME = "Purchase Receipt"


def execute():
	_create_workflow_masters()
	workflow = (
		frappe.get_doc("Workflow", WORKFLOW_NAME)
		if frappe.db.exists("Workflow", WORKFLOW_NAME)
		else frappe.new_doc("Workflow")
	)
	workflow.update(
		{
			"workflow_name": WORKFLOW_NAME,
			"document_type": "Purchase Receipt",
			"is_active": 1,
			"workflow_state_field": "workflow_state",
		}
	)
	workflow.set(
		"states",
		[
			{"state": "Draft", "doc_status": "0", "allow_edit": "Stock User"},
			{"state": "Approved", "doc_status": "1", "allow_edit": "Quality Manager"},
			{"state": "Partial QC Done", "doc_status": "1", "allow_edit": "Quality Manager"},
			{"state": "QC Completed - Fully Accepted", "doc_status": "1", "allow_edit": "Quality Manager"},
			{
				"state": "QC Completed - Partially Rejected",
				"doc_status": "1",
				"allow_edit": "Quality Manager",
			},
			{"state": "Return Submitted", "doc_status": "1", "allow_edit": "Stock User"},
		],
	)
	workflow.set(
		"transitions",
		[
			{
				"state": "Draft",
				"action": "Approve",
				"next_state": "Approved",
				"allowed": "Stock User",
				"allow_self_approval": 1,
				"condition": "not doc.is_return",
			},
			{
				"state": "Draft",
				"action": "Submit Return",
				"next_state": "Return Submitted",
				"allowed": "Stock User",
				"allow_self_approval": 1,
				"condition": "doc.is_return",
			},
		],
	)
	workflow.save(ignore_permissions=True)

	if not (
		frappe.db.has_column("Purchase Receipt", "workflow_state")
		and frappe.db.has_column("Purchase Receipt", "custom_qc_status")
	):
		return

	frappe.db.sql(
		"""
		UPDATE `tabPurchase Receipt`
		SET workflow_state = CASE
			WHEN is_return = 1 THEN 'Return Submitted'
			WHEN custom_qc_status = 'Partial QC Done' THEN 'Partial QC Done'
			WHEN custom_qc_status IN (
				'QC Completed', 'QC Completed - Fully Accepted',
				'QC Completed - Partially Rejected'
			) THEN CASE WHEN EXISTS (
				SELECT 1 FROM `tabIncoming QC Allocation` qca
				INNER JOIN `tabIncoming Quality Inspection` iqc ON iqc.name = qca.parent
				WHERE qca.purchase_receipt = `tabPurchase Receipt`.name
					AND iqc.docstatus = 1 AND qca.rejected_qty > 0
			) THEN 'QC Completed - Partially Rejected'
			ELSE 'QC Completed - Fully Accepted' END
			ELSE 'Approved'
		END,
		custom_qc_status = CASE
			WHEN is_return = 1 THEN ''
			WHEN custom_qc_status IN (
				'QC Completed', 'QC Completed - Fully Accepted',
				'QC Completed - Partially Rejected'
			) THEN CASE WHEN EXISTS (
				SELECT 1 FROM `tabIncoming QC Allocation` qca
				INNER JOIN `tabIncoming Quality Inspection` iqc ON iqc.name = qca.parent
				WHERE qca.purchase_receipt = `tabPurchase Receipt`.name
					AND iqc.docstatus = 1 AND qca.rejected_qty > 0
			) THEN 'QC Completed - Partially Rejected'
			ELSE 'QC Completed - Fully Accepted' END
			ELSE custom_qc_status
		END
		WHERE docstatus = 1
		"""
	)


def _create_workflow_masters():
	for state, style in (
		("Draft", "Primary"),
		("Approved", "Warning"),
		("Partial QC Done", "Warning"),
		("QC Completed - Fully Accepted", "Success"),
		("QC Completed - Partially Rejected", "Danger"),
		("Return Submitted", "Success"),
	):
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": state, "style": style}
			).insert(ignore_permissions=True)

	if not frappe.db.exists("Workflow Action Master", "Approve"):
		frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": "Approve"}).insert(
			ignore_permissions=True
		)

	if not frappe.db.exists("Workflow Action Master", "Submit Return"):
		frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": "Submit Return"}).insert(
			ignore_permissions=True
		)
