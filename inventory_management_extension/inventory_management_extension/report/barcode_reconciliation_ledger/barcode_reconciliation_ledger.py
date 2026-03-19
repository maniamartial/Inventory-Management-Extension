# Copyright (c) 2026, nei and contributors
# For license information, please see license.txt

"""
Barcode Reconciliation Ledger: Stock-Ledger-style view of barcode reconciliation activity.

Rows:
- Reconciliation: lines from Batch Barcode Reconciliation items (qty before / after / change).
- Missing: trackers marked missing (Material Issue path) from Missing Batch Barcode child table.
- Addition: new / unknown barcodes in Additional Batch Barcode (pending or received).
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{
			"fieldname": "posting_date",
			"label": _("Posting Date"),
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"fieldname": "posting_time",
			"label": _("Time"),
			"fieldtype": "Time",
			"width": 90,
		},
		{
			"fieldname": "entry_type",
			"label": _("Entry Type"),
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"fieldname": "reconciliation",
			"label": _("Batch Barcode Reconciliation"),
			"fieldtype": "Link",
			"options": "Batch Barcode Reconciliation",
			"width": 180,
		},
		{
			"fieldname": "docstatus",
			"label": _("Doc Status"),
			"fieldtype": "Data",
			"width": 90,
		},
		{
			"fieldname": "purpose",
			"label": _("Purpose"),
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"fieldname": "batch_barcode",
			"label": _("Batch Barcode Tracker"),
			"fieldtype": "Link",
			"options": "Batch Barcode Tracker",
			"width": 170,
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
			"fieldname": "warehouse",
			"label": _("Warehouse"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 120,
		},
		{
			"fieldname": "qty_before",
			"label": _("Qty Before"),
			"fieldtype": "Float",
			"width": 100,
		},
		{
			"fieldname": "qty_after",
			"label": _("Qty After"),
			"fieldtype": "Float",
			"width": 100,
		},
		{
			"fieldname": "qty_change",
			"label": _("Qty Change"),
			"fieldtype": "Float",
			"width": 100,
		},
		{
			"fieldname": "valuation_rate",
			"label": _("Valuation Rate"),
			"fieldtype": "Currency",
			"width": 100,
		},
		{
			"fieldname": "detail",
			"label": _("Detail"),
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"fieldname": "company",
			"label": _("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"width": 140,
		},
	]


def _docstatus_label(d):
	if d is None:
		return ""
	if int(d) == 0:
		return _("Draft")
	if int(d) == 1:
		return _("Submitted")
	if int(d) == 2:
		return _("Cancelled")
	return str(d)


def _build_rec_filters(filters, prefix="rec"):
	"""Shared filters on parent Batch Barcode Reconciliation."""
	conds = ["1=1"]
	params = {}
	if filters.get("company"):
		conds.append(f"{prefix}.company = %(company)s")
		params["company"] = filters["company"]
	if filters.get("from_date"):
		conds.append(f"{prefix}.posting_date >= %(from_date)s")
		params["from_date"] = getdate(filters["from_date"])
	if filters.get("to_date"):
		conds.append(f"{prefix}.posting_date <= %(to_date)s")
		params["to_date"] = getdate(filters["to_date"])
	if filters.get("reconciliation"):
		conds.append(f"{prefix}.name = %(reconciliation)s")
		params["reconciliation"] = filters["reconciliation"]
	if filters.get("purpose"):
		conds.append(f"{prefix}.purpose = %(purpose)s")
		params["purpose"] = filters["purpose"]
	# Ledger only shows submitted reconciliations (exclude draft and cancelled)
	conds.append(f"{prefix}.docstatus = 1")
	return " AND ".join(conds), params


def get_data(filters):
	rec_where, params = _build_rec_filters(filters)
	rows = []

	# --- 1) Reconciliation item lines (main ledger, like stock reconciliation lines)
	item_conds = [rec_where]
	item_filters = dict(params)
	if filters.get("item_code"):
		item_conds.append("item.item_code = %(item_code)s")
		item_filters["item_code"] = filters["item_code"]
	if filters.get("warehouse"):
		item_conds.append("item.warehouse = %(warehouse)s")
		item_filters["warehouse"] = filters["warehouse"]
	if filters.get("batch_no"):
		item_conds.append("item.batch_no = %(batch_no)s")
		item_filters["batch_no"] = filters["batch_no"]
	if filters.get("batch_barcode"):
		item_conds.append("item.batch_barcode = %(batch_barcode)s")
		item_filters["batch_barcode"] = filters["batch_barcode"]

	sql_items = f"""
		SELECT
			rec.posting_date AS posting_date,
			rec.posting_time AS posting_time,
			rec.name AS reconciliation,
			rec.docstatus AS docstatus,
			rec.purpose AS purpose,
			rec.company AS company,
			item.batch_barcode AS batch_barcode,
			item.barcode AS barcode,
			item.item_code AS item_code,
			item.batch_no AS batch_no,
			item.warehouse AS warehouse,
			IFNULL(item.current_qty, 0) AS qty_before,
			IFNULL(item.qty, 0) AS qty_after,
			(IFNULL(item.qty, 0) - IFNULL(item.current_qty, 0)) AS qty_change,
			IFNULL(item.valuation_rate, 0) AS valuation_rate,
			item.idx AS sort_idx
		FROM `tabBatch Barcode Reconciliation` rec
		INNER JOIN `tabBatch Barcode Reconciliation Item` item
			ON item.parent = rec.name
			AND item.parenttype = 'Batch Barcode Reconciliation'
		WHERE {' AND '.join(item_conds)}
	"""
	item_rows = frappe.db.sql(sql_items, item_filters, as_dict=True)
	for r in item_rows:
		qc = flt(r.get("qty_change"))
		detail = _("Stock count adjustment on reconciliation line")
		if qc > 0:
			detail = _("Addition: qty increased by {0}").format(qc)
		elif qc < 0:
			detail = _("Reduction: qty decreased by {0}").format(abs(qc))
		rows.append({
			"posting_date": r["posting_date"],
			"posting_time": r.get("posting_time"),
			"entry_type": "Reconciliation",
			"reconciliation": r["reconciliation"],
			"docstatus": _docstatus_label(r.get("docstatus")),
			"purpose": r.get("purpose") or "",
			"batch_barcode": r.get("batch_barcode"),
			"barcode": r.get("barcode"),
			"item_code": r.get("item_code"),
			"batch_no": r.get("batch_no"),
			"warehouse": r.get("warehouse"),
			"qty_before": flt(r.get("qty_before")),
			"qty_after": flt(r.get("qty_after")),
			"qty_change": qc,
			"valuation_rate": flt(r.get("valuation_rate")),
			"detail": detail,
			"company": r.get("company"),
			"_sort": (
				r["posting_date"],
				r["reconciliation"],
				0,
				r.get("sort_idx") or 0,
			),
		})

	# --- 2) Missing batch barcodes (physical missing → material issue path)
	m_conds = [rec_where]
	m_params = dict(params)
	if filters.get("warehouse"):
		m_conds.append("mb.warehouse = %(m_wh)s")
		m_params["m_wh"] = filters["warehouse"]
	if filters.get("batch_no"):
		m_conds.append("mb.batch = %(m_batch)s")
		m_params["m_batch"] = filters["batch_no"]
	if filters.get("batch_barcode"):
		m_conds.append("mb.barcode = %(m_bbt)s")
		m_params["m_bbt"] = filters["batch_barcode"]
	if filters.get("item_code"):
		m_conds.append("bbt.item_code = %(m_item)s")
		m_params["m_item"] = filters["item_code"]

	sql_missing = f"""
		SELECT
			rec.posting_date,
			rec.posting_time,
			rec.name AS reconciliation,
			rec.docstatus,
			rec.purpose,
			rec.company,
			mb.barcode AS batch_barcode,
			IFNULL(bbt.barcode, '') AS barcode,
			bbt.item_code AS item_code,
			mb.batch AS batch_no,
			IFNULL(mb.warehouse, bbt.warehouse) AS warehouse,
			IFNULL(mb.qty, IFNULL(bbt.qty, 0)) AS qty_before,
			0 AS qty_after,
			-IFNULL(mb.qty, IFNULL(bbt.qty, 0)) AS qty_change,
			mb.idx AS sort_idx,
			IFNULL(mb.batch_barcode_tracker_update, 0) AS tracker_updated
		FROM `tabBatch Barcode Reconciliation` rec
		INNER JOIN `tabMissing Batch Barcode` mb
			ON mb.parent = rec.name AND mb.parenttype = 'Batch Barcode Reconciliation'
		LEFT JOIN `tabBatch Barcode Tracker` bbt ON bbt.name = mb.barcode
		WHERE {' AND '.join(m_conds)}
	"""
	for r in frappe.db.sql(sql_missing, m_params, as_dict=True):
		qty = flt(r.get("qty_before"))
		issued = (
			_("Issued / removed from stock")
			if cint(r.get("tracker_updated"))
			else _("Pending material issue")
		)
		rows.append({
			"posting_date": r["posting_date"],
			"posting_time": r.get("posting_time"),
			"entry_type": "Missing",
			"reconciliation": r["reconciliation"],
			"docstatus": _docstatus_label(r.get("docstatus")),
			"purpose": r.get("purpose") or "",
			"batch_barcode": r.get("batch_barcode"),
			"barcode": r.get("barcode"),
			"item_code": r.get("item_code"),
			"batch_no": r.get("batch_no"),
			"warehouse": r.get("warehouse"),
			"qty_before": qty,
			"qty_after": 0.0,
			"qty_change": -qty,
			"valuation_rate": 0.0,
			"detail": _("Missing barcode — {0} (qty {1})").format(issued, qty),
			"company": r.get("company"),
			"_sort": (r["posting_date"], r["reconciliation"], 1, r.get("sort_idx") or 0),
		})

	# --- 3) Additional / new barcodes (scanned unknown → material receipt path)
	a_conds = [rec_where]
	a_params = dict(params)
	if filters.get("warehouse"):
		a_conds.append("ab.warehouse = %(a_wh)s")
		a_params["a_wh"] = filters["warehouse"]
	if filters.get("batch_no"):
		a_conds.append("ab.batch = %(a_batch)s")
		a_params["a_batch"] = filters["batch_no"]
	if filters.get("item_code"):
		a_conds.append("ab.item_code = %(a_item)s")
		a_params["a_item"] = filters["item_code"]
	# batch_barcode tracker filter: match transactional barcode string on additional row
	if filters.get("batch_barcode"):
		a_bbt = filters["batch_barcode"]
		t_barcode = frappe.db.get_value("Batch Barcode Tracker", a_bbt, "barcode")
		a_conds.append("(ab.barcode = %(a_bbt_name)s OR ab.barcode = %(a_tr_bar)s)")
		a_params["a_bbt_name"] = a_bbt
		a_params["a_tr_bar"] = t_barcode or a_bbt

	sql_add = f"""
		SELECT
			rec.posting_date,
			rec.posting_time,
			rec.name AS reconciliation,
			rec.docstatus,
			rec.purpose,
			rec.company,
			NULL AS batch_barcode,
			ab.barcode AS barcode,
			ab.item_code AS item_code,
			ab.batch AS batch_no,
			ab.warehouse AS warehouse,
			0 AS qty_before,
			IFNULL(ab.qty, 0) AS qty_after,
			IFNULL(ab.qty, 0) AS qty_change,
			ab.idx AS sort_idx,
			IFNULL(ab.batch_barcode_tracker_created, 0) AS tracker_created
		FROM `tabBatch Barcode Reconciliation` rec
		INNER JOIN `tabAdditional Batch Barcode` ab
			ON ab.parent = rec.name AND ab.parenttype = 'Batch Barcode Reconciliation'
		WHERE {' AND '.join(a_conds)}
	"""
	for r in frappe.db.sql(sql_add, a_params, as_dict=True):
		qty = flt(r.get("qty_after"))
		done = _("Tracker created / received") if cint(r.get("tracker_created")) else _("Pending material receipt")
		# Try to resolve batch_barcode (tracker name) after creation
		bbt_name = None
		if r.get("barcode"):
			bbt_name = frappe.db.get_value("Batch Barcode Tracker", {"barcode": r["barcode"]}, "name")
		rows.append({
			"posting_date": r["posting_date"],
			"posting_time": r.get("posting_time"),
			"entry_type": "Addition",
			"reconciliation": r["reconciliation"],
			"docstatus": _docstatus_label(r.get("docstatus")),
			"purpose": r.get("purpose") or "",
			"batch_barcode": bbt_name,
			"barcode": r.get("barcode"),
			"item_code": r.get("item_code"),
			"batch_no": r.get("batch_no"),
			"warehouse": r.get("warehouse"),
			"qty_before": 0.0,
			"qty_after": qty,
			"qty_change": qty,
			"valuation_rate": 0.0,
			"detail": _("New barcode — {0} (qty {1})").format(done, qty),
			"company": r.get("company"),
			"_sort": (r["posting_date"], r["reconciliation"], 2, r.get("sort_idx") or 0),
		})

	rows.sort(key=lambda x: (x["_sort"][0] or "", x["_sort"][1] or "", x["_sort"][2], x["_sort"][3]))
	for r in rows:
		r.pop("_sort", None)

	if filters.get("entry_type"):
		et = filters["entry_type"].strip()
		if et:
			rows = [r for r in rows if r.get("entry_type") == et]

	return rows
