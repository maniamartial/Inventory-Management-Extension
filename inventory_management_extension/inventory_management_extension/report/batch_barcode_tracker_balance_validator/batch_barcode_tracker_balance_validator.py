# Copyright (c) 2026, nei and contributors
# For license information, please see license.txt

"""
Batch Barcode Tracker Balance Validator
=======================================

Compares the quantity carried on Batch Barcode Tracker packs against the batch
wise stock balance, for the same Item / Batch / Warehouse combination, so that
any drift between the two can be spotted at a glance.

Barcode Qty
	Total Stock Qty (``qty``) of submitted (``docstatus = 1``) and unsold
	(``sold = 0``) Batch Barcode Tracker records. The batch of a tracker lives
	in ``lot_no`` when ``is_lot`` is set, otherwise in ``batch``.

Stock Qty
	Batch wise balance built from the stock ledger. Batches are read from
	``Serial and Batch Entry`` (reached through the Stock Ledger Entry's
	``serial_and_batch_bundle``) and, for records that still carry it, from
	``Stock Ledger Entry.batch_no``.

Rows where Barcode Qty and Stock Qty do not agree get a non-zero
``difference``; the report's client script renders those rows in red.

Group By
	``Batch`` (default) shows one row per Item / Batch / Warehouse. ``Item`` folds
	every batch and warehouse of an item into a single row. ``Batch Barcode
	Tracker`` shows one row per live barcode, named by its ``barcode``; there the
	Stock Qty, Difference and Status stay at the level of that barcode's Item /
	Batch / Warehouse bucket, so every barcode of an out of balance batch is
	flagged.

A ``batch_barcode_tracker`` filter narrows the report down to the Item / Batch /
Warehouse bucket that the picked tracker belongs to, so a single barcode can be
validated against the balance it should belong to.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

# Below this the two quantities are considered equal (float noise).
QTY_EPSILON = 0.00001

# How the report splits its rows: by batch (default), by item, or per barcode.
GROUP_BY_OPTIONS = ("Batch", "Item", "Batch Barcode Tracker")
DEFAULT_GROUP_BY = "Batch"


def execute(filters=None):
	filters = filters or {}
	columns = get_columns(filters)
	data = get_data(filters)
	return columns, data


def get_group_by(filters):
	"""Grouping asked for by the user, falling back to Batch."""
	group_by = (filters or {}).get("group_by") or DEFAULT_GROUP_BY

	for option in GROUP_BY_OPTIONS:
		if str(group_by).strip().lower() == option.lower():
			return option

	frappe.throw(_("Group By must be one of: {0}").format(", ".join(GROUP_BY_OPTIONS)))


def get_columns(filters=None):
	columns = [
		{
			"fieldname": "item_code",
			"label": _("Item Code"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 170,
		},
		{
			"fieldname": "item_name",
			"label": _("Item Name"),
			"fieldtype": "Data",
			"width": 190,
		},
		{
			"fieldname": "batch_no",
			"label": _("Batch"),
			"fieldtype": "Link",
			"options": "Batch",
			"width": 150,
		},
		{
			"fieldname": "warehouse",
			"label": _("Warehouse"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 170,
		},
	]

	# The per barcode view says which barcode each row stands for.
	if get_group_by(filters or {}) == "Batch Barcode Tracker":
		columns.extend(
			[
				{
					"fieldname": "barcode",
					"label": _("Barcode"),
					"fieldtype": "Data",
					"width": 180,
				},
				{
					"fieldname": "batch_barcode_tracker",
					"label": _("Batch Barcode Tracker"),
					"fieldtype": "Link",
					"options": "Batch Barcode Tracker",
					"width": 190,
				},
			]
		)

	columns.extend(
		[
			{
				"fieldname": "company",
				"label": _("Company"),
				"fieldtype": "Link",
				"options": "Company",
				"width": 150,
			},
			{
				"fieldname": "barcode_count",
				"label": _("Barcodes"),
				"fieldtype": "Int",
				"width": 90,
			},
			{
				"fieldname": "barcode_qty",
				"label": _("Barcode Qty"),
				"fieldtype": "Float",
				"width": 120,
			},
			{
				"fieldname": "stock_qty",
				"label": _("Stock Qty"),
				"fieldtype": "Float",
				"width": 120,
			},
			{
				"fieldname": "difference",
				"label": _("Difference (Stock - Barcode)"),
				"fieldtype": "Float",
				"width": 190,
			},
			{
				"fieldname": "status",
				"label": _("Status"),
				"fieldtype": "Data",
				"width": 200,
			},
		]
	)

	return columns


def get_data(filters):
	# A Batch Barcode Tracker filter narrows the report down to that tracker's
	# Item / Batch / Warehouse bucket.
	filters = _apply_tracker_scope(filters)
	group_by = get_group_by(filters)

	# Every grouping is built from the same Item / Batch / Warehouse comparison.
	buckets = _get_bucket_rows(filters)

	if group_by == "Item":
		data = _collapse_by_item(buckets)
	elif group_by == "Batch Barcode Tracker":
		data = _expand_by_tracker(buckets, filters)
	else:
		data = buckets

	if cint(filters.get("only_mismatch")):
		data = [row for row in data if abs(flt(row.get("difference"))) > QTY_EPSILON]

	return data


def _get_bucket_rows(filters):
	"""One labelled, comparable row per Item / Batch / Warehouse."""
	rows = {}

	for row in get_barcode_qty(filters):
		entry = rows.setdefault(_row_key(row), _blank_row(row))
		entry["barcode_count"] = cint(row.get("barcode_count"))
		entry["barcode_qty"] = flt(row.get("barcode_qty"))

	for row in get_stock_qty(filters):
		entry = rows.setdefault(_row_key(row), _blank_row(row))
		entry["stock_qty"] = flt(entry.get("stock_qty")) + flt(row.get("stock_qty"))

	item_names = _get_item_names({entry["item_code"] for entry in rows.values()})
	warehouse_companies = _get_warehouse_companies({entry["warehouse"] for entry in rows.values()})

	for entry in rows.values():
		entry["item_name"] = item_names.get(entry["item_code"])
		entry["company"] = warehouse_companies.get(entry["warehouse"])
		_finalise_row(entry)

	return sorted(rows.values(), key=_row_key)


def _collapse_by_item(buckets):
	"""Group By ``Item``: fold every batch and warehouse of an item into one row."""
	items = {}
	companies = {}

	for bucket in buckets:
		item_code = bucket["item_code"]
		entry = items.setdefault(
			item_code,
			{
				"item_code": item_code,
				"item_name": bucket.get("item_name"),
				"batch_no": None,
				"warehouse": None,
				"company": None,
				"barcode_count": 0,
				"barcode_qty": 0.0,
				"stock_qty": 0.0,
			},
		)
		entry["barcode_count"] += cint(bucket.get("barcode_count"))
		entry["barcode_qty"] += flt(bucket.get("barcode_qty"))
		entry["stock_qty"] += flt(bucket.get("stock_qty"))
		companies.setdefault(item_code, set()).add(bucket.get("company"))

	for item_code, entry in items.items():
		known_companies = companies[item_code] - {None}
		entry["company"] = known_companies.pop() if len(known_companies) == 1 else None
		_finalise_row(entry)

	return sorted(items.values(), key=_row_key)


def _expand_by_tracker(buckets, filters):
	"""Group By ``Batch Barcode Tracker``: one row per live barcode.

	Barcode Qty is that single barcode's quantity, while Stock Qty, Difference and
	Status stay at the level of its Item / Batch / Warehouse bucket, so every
	barcode of an out of balance batch is flagged.
	"""
	buckets_by_key = {_row_key(bucket): bucket for bucket in buckets}
	data = []

	for tracker in get_live_trackers(filters):
		bucket = buckets_by_key.get(_row_key(tracker), {})

		data.append(
			{
				"item_code": tracker.get("item_code"),
				"item_name": bucket.get("item_name"),
				"batch_no": tracker.get("batch_no"),
				"warehouse": tracker.get("warehouse"),
				"barcode": tracker.get("barcode"),
				"batch_barcode_tracker": tracker.get("batch_barcode_tracker"),
				"company": bucket.get("company"),
				"barcode_count": 1,
				"barcode_qty": flt(tracker.get("barcode_qty")),
				"stock_qty": flt(bucket.get("stock_qty")),
				"difference": flt(bucket.get("difference")),
				"status": bucket.get("status"),
			}
		)

	return data


def _apply_tracker_scope(filters):
	"""Turn a `batch_barcode_tracker` filter into its Item / Batch / Warehouse scope.

	Picking a single Batch Barcode Tracker narrows the report down to the bucket
	that tracker lives in, so the row still compares the full barcode quantity of
	that batch against its stock balance. The tracker's own Batch / Lot No takes
	precedence over any matching filter the user also typed in.
	"""
	tracker_name = filters.get("batch_barcode_tracker")
	if not tracker_name:
		return filters

	tracker = frappe.db.sql(
		f"""
		SELECT
			bbt.item_code AS item_code,
			bbt.warehouse AS warehouse,
			{_effective_batch_expr("bbt")} AS batch_no
		FROM `tabBatch Barcode Tracker` bbt
		WHERE bbt.name = %(tracker)s
		""",
		{"tracker": tracker_name},
		as_dict=True,
	)
	if not tracker:
		frappe.throw(_("Batch Barcode Tracker {0} does not exist").format(tracker_name))

	tracker = tracker[0]
	scope = {"item_code": tracker.item_code}
	if tracker.batch_no:
		scope["batch_no"] = tracker.batch_no
	if tracker.warehouse:
		scope["warehouse"] = tracker.warehouse

	scoped_filters = frappe._dict(filters)
	scoped_filters.update(scope)

	return scoped_filters


def _row_key(row):
	"""Item / Batch / Warehouse identify one comparable bucket."""
	return (row.get("item_code") or "", row.get("batch_no") or "", row.get("warehouse") or "")


def _blank_row(row):
	return {
		"item_code": row.get("item_code"),
		"batch_no": row.get("batch_no"),
		"warehouse": row.get("warehouse"),
		"barcode_count": 0,
		"barcode_qty": 0.0,
		"stock_qty": 0.0,
	}


def _finalise_row(entry):
	"""Reduce Barcode vs Stock to a difference and a status label."""
	entry["barcode_count"] = cint(entry.get("barcode_count"))
	entry["barcode_qty"] = flt(entry.get("barcode_qty"))
	entry["stock_qty"] = flt(entry.get("stock_qty"))
	entry["difference"] = flt(entry["stock_qty"] - entry["barcode_qty"], 6)
	entry["status"] = _get_status(entry["barcode_qty"], entry["stock_qty"], entry["difference"])
	return entry


def _get_status(barcode_qty, stock_qty, difference):
	if abs(difference) <= QTY_EPSILON:
		return _("Match")

	if not barcode_qty:
		return _("Stock without barcode")

	if not stock_qty:
		return _("Barcode without stock")

	if difference > 0:
		return _("Stock exceeds barcodes")

	return _("Barcodes exceed stock")


def _get_item_names(item_codes):
	item_codes = {item_code for item_code in item_codes if item_code}
	if not item_codes:
		return {}

	return dict(
		frappe.get_all(
			"Item",
			filters={"name": ["in", list(item_codes)]},
			fields=["name", "item_name"],
			as_list=True,
		)
	)


def _get_warehouse_companies(warehouses):
	warehouses = {warehouse for warehouse in warehouses if warehouse}
	if not warehouses:
		return {}

	return dict(
		frappe.get_all(
			"Warehouse",
			filters={"name": ["in", list(warehouses)]},
			fields=["name", "company"],
			as_list=True,
		)
	)


def _effective_batch_expr(alias="bbt"):
	"""A tracker's batch lives in lot_no for lots, otherwise in batch."""
	return f"IF(IFNULL({alias}.is_lot, 0) = 1, {alias}.lot_no, {alias}.batch)"


def get_barcode_qty(filters):
	"""Barcode Qty per Item / Batch / Warehouse, from live (unsold) trackers."""
	batch_expr = _effective_batch_expr("bbt")
	conditions, params = _barcode_conditions(filters)

	query = f"""
		SELECT
			bbt.item_code AS item_code,
			{batch_expr} AS batch_no,
			bbt.warehouse AS warehouse,
			COUNT(bbt.name) AS barcode_count,
			SUM(IFNULL(bbt.qty, 0)) AS barcode_qty
		FROM `tabBatch Barcode Tracker` bbt
		WHERE {" AND ".join(conditions)}
		GROUP BY bbt.item_code, {batch_expr}, bbt.warehouse
	"""

	return frappe.db.sql(query, params, as_dict=True)


def get_live_trackers(filters):
	"""One row per live (submitted, unsold) tracker, for the per barcode view."""
	batch_expr = _effective_batch_expr("bbt")
	conditions, params = _barcode_conditions(filters)

	query = f"""
		SELECT
			bbt.name AS batch_barcode_tracker,
			bbt.barcode AS barcode,
			bbt.item_code AS item_code,
			{batch_expr} AS batch_no,
			bbt.warehouse AS warehouse,
			IFNULL(bbt.qty, 0) AS barcode_qty
		FROM `tabBatch Barcode Tracker` bbt
		WHERE {" AND ".join(conditions)}
		ORDER BY bbt.item_code, {batch_expr}, bbt.warehouse, bbt.name
	"""

	return frappe.db.sql(query, params, as_dict=True)


def _barcode_conditions(filters):
	"""Shared filters for the live (submitted, unsold) Batch Barcode Tracker rows."""
	batch_expr = _effective_batch_expr("bbt")
	conditions = ["bbt.docstatus = 1", "IFNULL(bbt.sold, 0) = 0"]
	params = {}

	if filters.get("item_code"):
		conditions.append("bbt.item_code = %(item_code)s")
		params["item_code"] = filters["item_code"]

	if filters.get("batch_no"):
		conditions.append(f"{batch_expr} = %(batch_no)s")
		params["batch_no"] = filters["batch_no"]

	if filters.get("warehouse"):
		conditions.append("bbt.warehouse = %(warehouse)s")
		params["warehouse"] = filters["warehouse"]

	if filters.get("company"):
		conditions.append(
			"EXISTS (SELECT 1 FROM `tabWarehouse` wh"
			" WHERE wh.name = bbt.warehouse AND wh.company = %(company)s)"
		)
		params["company"] = filters["company"]

	return conditions, params


def get_stock_qty(filters):
	"""Batch wise stock balance per Item / Batch / Warehouse, from the ledger."""
	rows = []

	# Legacy path / "Use Serial & Batch Fields": batch sits on the Stock Ledger Entry.
	conditions, params = _stock_ledger_conditions(filters, "sle.batch_no")
	conditions.append("IFNULL(sle.serial_and_batch_bundle, '') = ''")
	rows.extend(
		frappe.db.sql(
			f"""
			SELECT
				sle.item_code AS item_code,
				sle.batch_no AS batch_no,
				sle.warehouse AS warehouse,
				SUM(IFNULL(sle.actual_qty, 0)) AS stock_qty
			FROM `tabStock Ledger Entry` sle
			WHERE {" AND ".join(conditions)}
			GROUP BY sle.item_code, sle.batch_no, sle.warehouse
			""",
			params,
			as_dict=True,
		)
	)

	# Serial and Batch Bundle path: batch sits on Serial and Batch Entry (signed qty).
	conditions, params = _stock_ledger_conditions(filters, "sbe.batch_no")
	rows.extend(
		frappe.db.sql(
			f"""
			SELECT
				sle.item_code AS item_code,
				sbe.batch_no AS batch_no,
				sle.warehouse AS warehouse,
				SUM(IFNULL(sbe.qty, 0)) AS stock_qty
			FROM `tabStock Ledger Entry` sle
			INNER JOIN `tabSerial and Batch Entry` sbe
				ON sbe.parent = sle.serial_and_batch_bundle
				AND sbe.parenttype = 'Serial and Batch Bundle'
			WHERE {" AND ".join(conditions)}
			GROUP BY sle.item_code, sbe.batch_no, sle.warehouse
			""",
			params,
			as_dict=True,
		)
	)

	return rows


def _stock_ledger_conditions(filters, batch_field):
	conditions = [
		"sle.is_cancelled = 0",
		"sle.docstatus < 2",
		f"IFNULL({batch_field}, '') != ''",
	]
	params = {}

	if filters.get("item_code"):
		conditions.append("sle.item_code = %(item_code)s")
		params["item_code"] = filters["item_code"]

	if filters.get("batch_no"):
		conditions.append(f"{batch_field} = %(batch_no)s")
		params["batch_no"] = filters["batch_no"]

	if filters.get("warehouse"):
		conditions.append("sle.warehouse = %(warehouse)s")
		params["warehouse"] = filters["warehouse"]

	if filters.get("company"):
		conditions.append("sle.company = %(company)s")
		params["company"] = filters["company"]

	return conditions, params
