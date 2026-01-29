# Copyright (c) 2026, nei and contributors
# For license information, please see license.txt


import frappe
from frappe import _


def execute(filters=None):
	"""Report showing the movement path of Batch Barcode Tracker via transaction history."""
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	"""Columns: Batch Barcode Tracker info + each transaction step in the path."""
	return [
		{
			"fieldname": "batch_barcode_tracker",
			"label": _("Batch Barcode Tracker"),
			"fieldtype": "Link",
			"options": "Batch Barcode Tracker",
			"width": 180,
		},
		{
			"fieldname": "barcode",
			"label": _("Barcode"),
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"fieldname": "item_code",
			"label": _("Item Code"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 120,
		},
		{
			"fieldname": "batch_no",
			"label": _("Batch No"),
			"fieldtype": "Link",
			"options": "Batch",
			"width": 120,
		},
		{
			"fieldname": "qty",
			"label": _("Qty"),
			"fieldtype": "Float",
			"width": 80,
		},
		{
			"fieldname": "warehouse",
			"label": _("Warehouse"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 120,
		},
		{
			"fieldname": "sold",
			"label": _("Sold"),
			"fieldtype": "Check",
			"width": 60,
		},
		{
			"fieldname": "manufactured_date",
			"label": _("Manufactured Date"),
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"fieldname": "certification",
			"label": _("Certification"),
			"fieldtype": "Link",
			"options": "Main Certification",
			"width": 140,
		},
		{
			"fieldname": "transaction_type",
			"label": _("Transaction Type"),
			"fieldtype": "Data",
			"width": 100,
		},
		{
			"fieldname": "reference_document_type",
			"label": _("Reference Document Type"),
			"fieldtype": "Link",
			"options": "DocType",
			"width": 140,
		},
		{
			"fieldname": "reference_document_name",
			"label": _("Reference Document Name"),
			"fieldtype": "Dynamic Link",
			"options": "reference_document_type",
			"width": 150,
		},
		{
			"fieldname": "posting_date",
			"label": _("Posting Date"),
			"fieldtype": "Date",
			"width": 100,
		},
	]


def get_data(filters):
	"""Get movement path: join Batch Barcode Tracker with its transaction history."""
	filters = filters or {}
	conditions = ["bbt.docstatus = 1"]

	if filters.get("item_code"):
		conditions.append("bbt.item_code = %(item_code)s")
	if filters.get("batch_no"):
		conditions.append("bbt.batch = %(batch_no)s")
	if filters.get("batch_barcode_tracker"):
		conditions.append("bbt.name = %(batch_barcode_tracker)s")
	if filters.get("manufactured_date"):
		conditions.append("bbt.posting_date = %(manufactured_date)s")

	where_clause = " AND ".join(conditions)

	# Query: one row per transaction in history, with parent barcode tracker details
	# Certification comes from Batch.custom_certification
	sql = """
		SELECT
			bbt.name AS batch_barcode_tracker,
			bbt.barcode,
			bbt.item_code,
			bbt.batch AS batch_no,
			bbt.qty,
			bbt.warehouse,
			bbt.sold,
			bbt.posting_date AS manufactured_date,
			batch.custom_certification AS certification,
			txn.transaction_type,
			txn.reference_document_type,
			txn.reference_document_name,
			txn.posting_date
		FROM `tabBatch Barcode Tracker` bbt
		INNER JOIN `tabBatch Barcode Tracker Transaction` txn
			ON txn.parent = bbt.name
			AND txn.parenttype = 'Batch Barcode Tracker'
		LEFT JOIN `tabBatch` batch ON batch.name = bbt.batch
		WHERE {where_clause}
		ORDER BY bbt.name, txn.posting_date, txn.idx
	""".format(where_clause=where_clause)

	data = frappe.db.sql(sql, filters, as_dict=1)
	return data
