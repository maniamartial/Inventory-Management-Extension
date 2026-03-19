// Copyright (c) 2026, nei and contributors
// For license information, please see license.txt

frappe.query_reports["Barcode Reconciliation Ledger"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "reconciliation",
			label: __("Batch Barcode Reconciliation"),
			fieldtype: "Link",
			options: "Batch Barcode Reconciliation",
			get_query: function () {
				return { filters: { docstatus: 1 } };
			},
		},
		{
			fieldname: "batch_barcode",
			label: __("Batch Barcode Tracker"),
			fieldtype: "Link",
			options: "Batch Barcode Tracker",
		},
		{
			fieldname: "item_code",
			label: __("Item Code"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "batch_no",
			label: __("Batch No"),
			fieldtype: "Link",
			options: "Batch",
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
		},
		{
			fieldname: "entry_type",
			label: __("Entry Type"),
			fieldtype: "Select",
			options: "\n\nReconciliation\nMissing\nAddition",
		},
		{
			fieldname: "purpose",
			label: __("Purpose"),
			fieldtype: "Select",
			options: "\nOpening Stock\nStock Reconciliation",
		},
	],
};
