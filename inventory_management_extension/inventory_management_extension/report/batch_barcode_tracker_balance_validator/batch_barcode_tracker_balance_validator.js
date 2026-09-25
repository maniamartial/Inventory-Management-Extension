// Copyright (c) 2026, nei and contributors
// For license information, please see license.txt

frappe.query_reports["Batch Barcode Tracker Balance Validator"] = {
	filters: [
		{
			fieldname: "group_by",
			label: __("Group By"),
			fieldtype: "Select",
			options: "Batch\nItem\nBatch Barcode Tracker",
			default: "Batch",
			reqd: 1,
			description: __(
				"Batch: one row per Item / Batch / Warehouse. Item: one row per item. Batch Barcode Tracker: one row per barcode, with Stock Qty, Difference and Status kept at batch level."
			),
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
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
			fieldname: "batch_barcode_tracker",
			label: __("Batch Barcode Tracker"),
			fieldtype: "Link",
			options: "Batch Barcode Tracker",
			description: __("Narrow the report down to the Item / Batch / Warehouse of one barcode."),
		},
		{
			fieldname: "only_mismatch",
			label: __("Only Show Differences"),
			fieldtype: "Check",
			default: 1,
			description: __("Show only Item / Batch / Warehouse combinations where Barcode Qty and Stock Qty differ."),
		},
	],

	// Render every cell of a mismatching row in red so differences stand out.
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		const difference = data ? flt(data.difference) : 0;

		if (Math.abs(difference) > 0.00001) {
			value = `<span class="text-danger">${value}</span>`;
		}

		return value;
	},
};
