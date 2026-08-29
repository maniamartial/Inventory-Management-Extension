// Copyright (c) 2025, nei and contributors
// For license information, please see license.txt

frappe.ui.form.on("Batch Barcode Tracker", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Reconcile Stock Entries"), function() {
				prompt_date_range_and_enqueue(frm);
			});
		}
	}
});

function prompt_date_range_and_enqueue(frm) {
	let d = new frappe.ui.Dialog({
		title: __("Reconcile Stock Entries"),
		fields: [
			{
				fieldname: "start_date",
				label: __("Stock Entry Created From"),
				fieldtype: "Date",
				reqd: 1,
				description: __("Uses when the Stock Entry was created, not posting date.")
			},
			{
				fieldname: "end_date",
				label: __("Stock Entry Created To"),
				fieldtype: "Date",
				reqd: 1
			}
		],
		primary_action_label: __("Reconcile in Background"),
		primary_action: function(values) {
			d.hide();
			enqueue_reconcile_all(frm, values.start_date, values.end_date);
		}
	});

	d.show();
}

function enqueue_reconcile_all(frm, start_date, end_date) {
	frappe.call({
		method: "inventory_management_extension.inventory_management_extension.utils.enqueue_reconcile_all_batch_barcodes",
		args: {
			start_date: start_date,
			end_date: end_date
		},
		freeze: true,
		freeze_message: __("Enqueuing reconciliation job..."),
		callback: function(r) {
			if (r.message && r.message.job_id) {
				frappe.msgprint({
					title: __("Reconciliation Queued"),
					message: __("Background reconciliation job {0} has been queued for Stock Entries created between {1} and {2}.", [r.message.job_id, start_date, end_date]),
					indicator: "blue"
				});
			} else {
				frappe.msgprint({
					title: __("Reconciliation Queued"),
					message: __("Background reconciliation job has been queued for Stock Entries created between {0} and {1}.", [start_date, end_date]),
					indicator: "blue"
				});
			}
		},
		error: function(r) {
			frappe.msgprint({
				title: __("Failed to Queue Job"),
				message: __("An error occurred while enqueuing the reconciliation job: {0}", [r.message]),
				indicator: "red"
			});
		}
	});
}
