# Copyright (c) 2025, nei and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from inventory_management_extension.inventory_management_extension.utils import (
    mark_barcode_as_sold,
    update_barcode_warehouse_and_add_transfer,
)


class BatchBarcodeTracker(Document):
	@frappe.whitelist()
	def reconcile_stock_entries(self, start_date=None, end_date=None):
		"""
		Iterate through submitted Stock Entries (Repack, Manufacture, Material
		Transfer, Material Issue, etc.) where the item carried this tracker's
		barcode as `custom_transaction_barcode` but the user did NOT select
		`custom_batch_barcode`. This happens when users forget to pick the batch
		barcode field, so the tracker was never marked sold / transferred.

		Optionally filter by parent Stock Entry posting_date within
		[start_date, end_date].

		Applies the exact same update logic used on stock entry submit:
		- s_warehouse + t_warehouse  -> Transfer (warehouse + Transfer transaction)
		- s_warehouse only           -> Consumption / Issue (mark as sold)
		- t_warehouse only           -> skipped (this tracker was created, not consumed)

		Updates are skipped if a transaction for that Stock Entry already exists
		on this tracker, making the button safe to run repeatedly.
		"""
		if not self.barcode:
			frappe.throw("Barcode is required to reconcile stock entries.")

		date_filters = ""
		params = [self.barcode]

		if start_date:
			date_filters += " AND se.posting_date >= %s"
			params.append(start_date)
		if end_date:
			date_filters += " AND se.posting_date <= %s"
			params.append(end_date)

		# Find submitted Stock Entry rows that carried this barcode as the
		# transaction barcode but never picked the batch barcode field.
		# Raw SQL is used because (batch_barcode IN ('', NULL)) does not match
		# NULL in a standard frappe.get_all filter.
		rows = frappe.db.sql(
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
			""" + date_filters + """
			ORDER BY sed.creation ASC
			""",
			params,
			as_dict=True,
		)

		# Cache stock entry types per parent
		stock_entry_types = {}

		processed = []
		skipped = []

		for row in rows:
			parent = row.get("parent")
			if parent not in stock_entry_types:
				stock_entry_types[parent] = frappe.db.get_value(
					"Stock Entry", parent, "stock_entry_type"
				)

			stock_entry_type = stock_entry_types.get(parent)
			has_source = bool(row.get("s_warehouse"))
			has_target = bool(row.get("t_warehouse"))

			# Never touch rows that only received stock (tracker was created on submit).
			if not has_source:
				skipped.append({
					"stock_entry": parent,
					"item_code": row.get("item_code"),
					"reason": "Target-only row (tracker created, nothing to reconcile)",
				})
				continue

			# Idempotency: skip if this tracker already recorded a transaction
			# for this Stock Entry (Consumption / Issue / Transfer / etc.).
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
				continue

			try:
				if has_source and has_target:
					# Same barcode moved s -> t: transfer warehouse + Transfer transaction
					update_barcode_warehouse_and_add_transfer(
						self.name,
						row.get("t_warehouse"),
						row.get("s_warehouse"),
						"Stock Entry",
						parent,
					)
					action = "Transfer"
				else:
					# Consumption / Issue
					if stock_entry_type in ("Manufacture", "Repack"):
						transaction_type = "Consumption"
					elif stock_entry_type == "Material Issue":
						transaction_type = "Issue"
					else:
						transaction_type = "Issue"

					mark_barcode_as_sold(
						self.name,
						"Stock Entry",
						parent,
						transaction_type=transaction_type,
						warehouse=row.get("s_warehouse"),
					)
					action = transaction_type

				# Stamp the resolved batch barcode back onto the submitted row so
				# future submissions / reconciles resolve it automatically.
				frappe.db.set_value(
					"Stock Entry Detail", row.get("name"), "custom_batch_barcode", self.name
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

		return {
			"tracker": self.name,
			"barcode": self.barcode,
			"processed": processed,
			"skipped": skipped,
			"processed_count": len(processed),
			"skipped_count": len(skipped),
		}
