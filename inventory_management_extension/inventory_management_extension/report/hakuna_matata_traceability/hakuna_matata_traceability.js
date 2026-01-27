// Copyright (c) 2026, nei and contributors
// For license information, please see license.txt

frappe.query_reports["Hakuna Matata Traceability"] = {
	"filters": [
		{
			"fieldname": "item_code",
			"label": __("Item Code"),
			"fieldtype": "Link",
			"options": "Item",
		},
		{
			"fieldname": "batch_no",
			"label": __("Batch No"),
			"fieldtype": "Link",
			"options": "Batch",
		},
		{
			"fieldname": "batch_barcode_tracker",
			"label": __("Batch Barcode Tracker"),
			"fieldtype": "Link",
			"options": "Batch Barcode Tracker",
		},
		{
			"fieldname": "manufactured_date",
			"label": __("Manufactured Date"),
			"fieldtype": "Date",
		},
	],
};
