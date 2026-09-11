# Copyright (c) 2025, nei and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt
from inventory_management_extension.inventory_management_extension.utils import (
    mark_barcode_as_sold,
    update_barcode_warehouse_and_add_transfer,
)


class BatchBarcodeTracker(Document):
	def validate(self):
		self._set_uom_and_qty_totals()

	def _set_uom_and_qty_totals(self):
		"""
		Keep Stock UOM and Transaction UOM totals consistent.

		- `uom` / `qty` = Stock UOM / Stock Qty
		- `transaction_uom` / `transaction_qty` = UOM used on the creating document
		- `conversion_factor`: 1 Transaction UOM = conversion_factor × Stock UOM
		"""
		if self.item_code and not self.uom:
			self.uom = frappe.db.get_value("Item", self.item_code, "stock_uom")

		if not self.transaction_uom:
			self.transaction_uom = self.uom

		conversion_factor = flt(self.conversion_factor)
		if conversion_factor <= 0:
			conversion_factor = 1.0
			if (
				self.item_code
				and self.transaction_uom
				and self.uom
				and self.transaction_uom != self.uom
			):
				cf = frappe.db.get_value(
					"UOM Conversion Detail",
					{"parent": self.item_code, "uom": self.transaction_uom},
					"conversion_factor",
				)
				if cf:
					conversion_factor = flt(cf)
			self.conversion_factor = conversion_factor
		else:
			self.conversion_factor = conversion_factor

		transaction_qty = flt(self.transaction_qty)
		stock_qty = flt(self.qty)

		# Prefer deriving the missing side from the other using conversion.
		if transaction_qty and not stock_qty:
			self.qty = transaction_qty * self.conversion_factor
		elif stock_qty and not transaction_qty:
			self.transaction_qty = (
				stock_qty / self.conversion_factor if self.conversion_factor else stock_qty
			)
		elif transaction_qty and stock_qty:
			# Keep both; if they disagree, trust transaction_qty × conversion
			# when conversion is set and UOMs differ.
			expected_stock = transaction_qty * self.conversion_factor
			if abs(expected_stock - stock_qty) > 0.00001 and self.transaction_uom != self.uom:
				self.qty = expected_stock
		elif stock_qty and not self.transaction_qty:
			self.transaction_qty = stock_qty
			self.transaction_uom = self.transaction_uom or self.uom
			self.conversion_factor = self.conversion_factor or 1

	@frappe.whitelist()
	def reconcile_stock_entries(self, start_date=None, end_date=None):
		"""
		Iterate through submitted Stock Entries (Repack, Manufacture, Material
		Transfer, Material Issue, etc.) that belong to this tracker.

		Match order:
		1. `custom_transaction_barcode` equals this tracker's barcode, and
		   `custom_batch_barcode` was left empty (user forgot to pick the tracker).
		2. If still unsold: consume-only rows (source warehouse, no target) with
		   the same item, batch, and quantity. Barcodes are consumed in full, so
		   this recovers rows typed with a wrong / different transaction barcode.

		Optionally filter by parent Stock Entry creation date within
		[start_date, end_date] (not posting_date — posting can be backdated).

		A consume/transfer Stock Entry is only eligible if it was created
		at or after this tracker. If posting_date is earlier, the tracker
		simply did not exist yet at that backdated date.

		Applies the exact same update logic used on stock entry submit:
		- s_warehouse + t_warehouse  -> Transfer (warehouse + Transfer transaction)
		- s_warehouse only           -> Consumption / Issue (mark as sold)
		- t_warehouse only           -> skipped (this tracker was created, not consumed)

		Updates are skipped if a transaction for that Stock Entry already exists
		on this tracker, making the button safe to run repeatedly.
		"""
		if not self.barcode:
			frappe.throw("Barcode is required to reconcile stock entries.")

		processed = []
		skipped = []
		seen_row_names = set()

		barcode_rows = self._get_rows_by_transaction_barcode(start_date, end_date)
		for row in barcode_rows:
			self._reconcile_stock_entry_row(
				row, processed, skipped, seen_row_names, allow_transfer=True
			)

		# Full consume by item + batch + qty when the barcode on the stock entry
		# does not match this tracker (e.g. a mistyped transaction barcode).
		if not cint(self.sold):
			qty_rows = self._get_rows_by_item_batch_qty(start_date, end_date)
			for row in qty_rows:
				if cint(self.sold):
					break
				self._reconcile_stock_entry_row(
					row, processed, skipped, seen_row_names, allow_transfer=False
				)

		return {
			"tracker": self.name,
			"barcode": self.barcode,
			"processed": processed,
			"skipped": skipped,
			"processed_count": len(processed),
			"skipped_count": len(skipped),
		}

	def _date_filter_sql(self, start_date=None, end_date=None):
		"""Filter by when the Stock Entry was created, not posting_date."""
		date_filters = ""
		params = []
		if start_date:
			date_filters += " AND DATE(se.creation) >= %s"
			params.append(start_date)
		if end_date:
			date_filters += " AND DATE(se.creation) <= %s"
			params.append(end_date)
		return date_filters, params

	def _created_after_tracker_sql(self):
		"""Stock Entry must already have this tracker available (creation clock)."""
		if not self.creation:
			return "", []
		return " AND se.creation >= %s", [self.creation]

	def _get_rows_by_transaction_barcode(self, start_date=None, end_date=None):
		date_filters, date_params = self._date_filter_sql(start_date, end_date)
		created_sql, created_params = self._created_after_tracker_sql()
		return frappe.db.sql(
			"""
			SELECT
				sed.name,
				sed.parent,
				sed.item_code,
				sed.qty,
				sed.s_warehouse,
				sed.t_warehouse,
				sed.batch_no,
				sed.custom_transaction_barcode
			FROM `tabStock Entry Detail` sed
			INNER JOIN `tabStock Entry` se ON se.name = sed.parent
			WHERE sed.custom_transaction_barcode = %s
				AND sed.docstatus = 1
				AND (sed.custom_batch_barcode IS NULL OR sed.custom_batch_barcode = '')
			""" + created_sql + date_filters + """
			ORDER BY sed.creation ASC
			""",
			[self.barcode] + created_params + date_params,
			as_dict=True,
		)

	def _get_rows_by_item_batch_qty(self, start_date=None, end_date=None):
		"""
		Consume-only Stock Entry rows with the same item, batch, and qty.
		Does not require the transaction barcode to equal this tracker.

		Qty match uses Stock Qty (`qty`) against SED transfer_qty / stock qty,
		and also Transaction Qty against SED.qty for legacy / mistyped rows.

		Only Stock Entries created after this tracker are considered. A
		backdated posting_date before the tracker exists is ignored.
		"""
		batch_no = self.lot_no if cint(self.is_lot) else self.batch
		stock_qty = flt(self.qty)
		transaction_qty = flt(self.transaction_qty) or stock_qty
		if not self.item_code or not batch_no or (stock_qty == 0 and transaction_qty == 0):
			return []

		date_filters, date_params = self._date_filter_sql(start_date, end_date)
		created_sql, created_params = self._created_after_tracker_sql()
		params = [self.item_code, batch_no, stock_qty, transaction_qty]

		warehouse_filter = ""
		if self.warehouse:
			warehouse_filter = " AND sed.s_warehouse = %s"
			params.append(self.warehouse)

		return frappe.db.sql(
			"""
			SELECT
				sed.name,
				sed.parent,
				sed.item_code,
				sed.qty,
				sed.s_warehouse,
				sed.t_warehouse,
				sed.batch_no,
				sed.custom_transaction_barcode
			FROM `tabStock Entry Detail` sed
			INNER JOIN `tabStock Entry` se ON se.name = sed.parent
			WHERE sed.docstatus = 1
				AND sed.item_code = %s
				AND sed.batch_no = %s
				AND (
					ABS(IFNULL(NULLIF(sed.transfer_qty, 0), sed.qty) - %s) < 0.00001
					OR ABS(sed.qty - %s) < 0.00001
				)
				AND sed.s_warehouse IS NOT NULL
				AND sed.s_warehouse != ''
				AND (sed.t_warehouse IS NULL OR sed.t_warehouse = '')
				AND (sed.custom_batch_barcode IS NULL OR sed.custom_batch_barcode = '')
			""" + warehouse_filter + created_sql + date_filters + """
			ORDER BY sed.creation ASC
			""",
			params + created_params + date_params,
			as_dict=True,
		)

	def _reconcile_stock_entry_row(
		self, row, processed, skipped, seen_row_names, allow_transfer=True
	):
		row_name = row.get("name")
		if row_name in seen_row_names:
			return
		seen_row_names.add(row_name)

		parent = row.get("parent")
		has_source = bool(row.get("s_warehouse"))
		has_target = bool(row.get("t_warehouse"))

		if not has_source:
			skipped.append({
				"stock_entry": parent,
				"item_code": row.get("item_code"),
				"reason": "Target-only row (tracker created, nothing to reconcile)",
			})
			return

		if has_source and has_target and not allow_transfer:
			skipped.append({
				"stock_entry": parent,
				"item_code": row.get("item_code"),
				"reason": "Transfer row skipped for item/batch/qty match",
			})
			return

		# Another tracker already owns this typed barcode — do not steal it.
		typed_barcode = row.get("custom_transaction_barcode")
		if typed_barcode and typed_barcode != self.barcode:
			if frappe.db.exists("Batch Barcode Tracker", typed_barcode):
				skipped.append({
					"stock_entry": parent,
					"item_code": row.get("item_code"),
					"reason": f"Transaction barcode belongs to tracker {typed_barcode}",
				})
				return

		already_processed = frappe.db.exists(
			"Batch Barcode Tracker Transaction",
			{
				"parent": self.name,
				"parenttype": "Batch Barcode Tracker",
				"reference_document_type": "Stock Entry",
				"reference_document_name": parent,
			},
		)
		if already_processed:
			skipped.append({
				"stock_entry": parent,
				"item_code": row.get("item_code"),
				"reason": "Stock Entry already reconciled on this tracker",
			})
			return

		stock_entry_type = frappe.db.get_value("Stock Entry", parent, "stock_entry_type")

		try:
			if has_source and has_target:
				update_barcode_warehouse_and_add_transfer(
					self.name,
					row.get("t_warehouse"),
					row.get("s_warehouse"),
					"Stock Entry",
					parent,
				)
				action = "Transfer"
			else:
				if stock_entry_type in ("Manufacture", "Repack"):
					transaction_type = "Consumption"
				else:
					transaction_type = "Issue"

				mark_barcode_as_sold(
					self.name,
					"Stock Entry",
					parent,
					transaction_type=transaction_type,
					warehouse=row.get("s_warehouse"),
				)
				self.sold = 1
				action = transaction_type

			frappe.db.set_value(
				"Stock Entry Detail", row_name, "custom_batch_barcode", self.name
			)

			processed.append({
				"stock_entry": parent,
				"item_code": row.get("item_code"),
				"action": action,
				"qty": row.get("qty"),
			})
		except Exception as e:
			frappe.log_error(
				f"Batch Barcode Tracker reconciliation failed for {parent} "
				f"on tracker {self.name}: {e}",
				"Batch Barcode Tracker Reconcile",
			)
			skipped.append({
				"stock_entry": parent,
				"item_code": row.get("item_code"),
				"reason": f"Error: {e}",
			})
