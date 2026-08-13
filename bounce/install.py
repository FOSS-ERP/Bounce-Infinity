from bounce.patches.v0_0.configure_purchase_receipt_qc_workflow import execute as configure_qc_workflow


def after_install():
	configure_qc_workflow()
