# Copyright (c) 2026, nei and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, cint, get_datetime_str
from frappe import _


class BatchBarcodeReconciliation(Document):
	"""
	Batch Barcode Reconciliation Document
	
	Handles stock reconciliation with barcode scanning and automatic 
	Batch Barcode Tracker updates on submission.
	"""

	def validate(self):
		"""Validate the reconciliation document before saving"""
		self.validate_items()
		self.calculate_differences()

	def validate_items(self):
		"""Validate that all items have required fields"""
		if not self.items:
			frappe.throw(_("Please add at least one item to reconcile"))
		
		for idx, item in enumerate(self.items, 1):
			if not item.item_code:
				frappe.throw(_("Row {0}: Item Code is required").format(idx))
			if not item.warehouse:
				frappe.throw(_("Row {0}: Warehouse is required").format(idx))
			if item.qty is None:
				frappe.throw(_("Row {0}: Quantity is required").format(idx))

	def calculate_differences(self):
		"""Calculate quantity and amount differences"""
		for item in self.items:
			if item.current_qty is None:
				item.current_qty = 0
			if item.current_valuation_rate is None:
				item.current_valuation_rate = 0
			if item.qty is None:
				item.qty = 0
			if item.valuation_rate is None:
				item.valuation_rate = 0
			
			# Calculate differences
			item.quantity_difference = flt(item.qty) - flt(item.current_qty)
			item.current_amount = flt(item.current_qty) * flt(item.current_valuation_rate)
			item.amount = flt(item.qty) * flt(item.valuation_rate)
			item.amount_difference = flt(item.amount) - flt(item.current_amount)

	def on_submit(self):
		"""
		On submission:
		1. Update Batch Barcode Tracker quantities
		2. Create transaction records
		3. Mark reconciliation as complete
		"""
		self.update_batch_barcode_tracker()

	def update_batch_barcode_tracker(self):
		"""
		Update Batch Barcode Tracker records with reconciled quantities.
		Directly transfers qty and quantity_difference from reconciliation items.
		"""
		if not self.items:
			return
		
		for item in self.items:
			# Only update if we have a batch barcode reference
			if not item.batch_barcode:
				continue
			
			try:
				# Direct transfer: Use qty from reconciliation (already calculated)
				new_qty = flt(item.qty)
				qty_change = flt(item.quantity_difference)  # Already calculated in form
				
				# Update the quantity field using frappe.db.set_value
				frappe.db.set_value("Batch Barcode Tracker", item.batch_barcode, "qty", new_qty)
				
				# Get the Batch Barcode Tracker record
				tracker = frappe.get_doc("Batch Barcode Tracker", item.batch_barcode)
				
				# Add transaction to child table using append()
				tracker.append("transaction_history", {
					"transaction_type": "Reconciliation",
					"reference_document_type": "Batch Barcode Reconciliation",
					"reference_document_name": self.name,
					"warehouse": item.warehouse,
					"posting_date": self.posting_date,
					"posting_time": self.posting_time,
					"reconciliation": 1,
					"quantity_change": qty_change,
				})
				
				# Save the updated tracker with transaction
				tracker.save(ignore_permissions=True)
				
			except frappe.DoesNotExistError:
				frappe.log_error(
					_("Batch Barcode Tracker {0} not found").format(item.batch_barcode),
					"Batch Barcode Reconciliation - Tracker Not Found"
				)
			except Exception as e:
				frappe.log_error(
					str(e),
					"Batch Barcode Reconciliation - Update Error for {0}".format(item.batch_barcode)
				)
		
		# Show success message
		frappe.msgprint(
			_("All scanned items have been updated in Batch Barcode Tracker with their new quantities and transaction records."),
			title=_("Batch Barcode Tracker Updated"),
			indicator="green"
		)

	def on_cancel(self):
		"""
		When reconciliation is cancelled, revert the tracker updates
		and remove the transaction records created by this reconciliation
		"""
		self.revert_batch_barcode_tracker()

	def revert_batch_barcode_tracker(self):
		"""
		Revert Batch Barcode Tracker records when reconciliation is cancelled.
		Reverts qty back to old value by calculating: old_qty = current_qty - quantity_change
		Removes transaction records created by this reconciliation.
		"""
		if not self.items:
			return
		
		for item in self.items:
			# Only revert if we have a batch barcode reference
			if not item.batch_barcode:
				continue
			
			try:
				# Get the Batch Barcode Tracker record
				tracker = frappe.get_doc("Batch Barcode Tracker", item.batch_barcode)
				
				# Calculate old qty by subtracting the quantity_difference
				# quantity_difference was: new_qty - old_qty
				# So: old_qty = current_qty - quantity_difference
				quantity_change = flt(item.quantity_difference)
				old_qty = flt(tracker.qty) - quantity_change
				
				# Revert qty back to old value using frappe.db.set_value
				frappe.db.set_value("Batch Barcode Tracker", item.batch_barcode, "qty", old_qty)
				
				# Get fresh tracker to remove transactions
				tracker = frappe.get_doc("Batch Barcode Tracker", item.batch_barcode)
				
				# Remove the transaction records created by this reconciliation
				if tracker.transaction_history:
					# Keep only transactions NOT created by this reconciliation
					tracker.transaction_history = [
						t for t in tracker.transaction_history
						if not (t.get("reference_document_type") == "Batch Barcode Reconciliation" 
						        and t.get("reference_document_name") == self.name)
					]
				
				# Save the tracker with reverted qty and removed transactions
				tracker.save(ignore_permissions=True)
				
			except frappe.DoesNotExistError:
				frappe.log_error(
					_("Batch Barcode Tracker {0} not found during cancellation").format(item.batch_barcode),
					"Batch Barcode Reconciliation - Revert Error"
				)
			except Exception as e:
				frappe.log_error(
					str(e),
					"Batch Barcode Reconciliation - Revert Error for {0}".format(item.batch_barcode)
				)
		
		# Show success message
		frappe.msgprint(
			_("Batch Barcode Tracker quantities and transaction records have been reverted."),
			title=_("Reconciliation Cancelled"),
			indicator="orange"
		)


@frappe.whitelist()
def get_items(warehouse, posting_date, posting_time, company, item_code=None, ignore_empty_stock=False):
	"""
	Fetch items from a warehouse with their current quantities
	
	Args:
		warehouse: Warehouse to fetch items from
		posting_date: Posting date for stock calculation
		posting_time: Posting time for stock calculation
		company: Company name
		item_code: Optional - specific item code to fetch
		ignore_empty_stock: Optional - skip items with zero quantity
	
	Returns:
		List of items with quantities
	"""
	from erpnext.stock.utils import get_stock_balance
	
	if not warehouse:
		frappe.throw(_("Warehouse is required"))
	
	if not posting_date:
		frappe.throw(_("Posting Date is required"))
	
	filters = {
		"warehouse": warehouse,
		"company": company,
	}
	
	if item_code:
		filters["name"] = item_code
	
	items = frappe.get_list(
		"Item",
		filters=filters,
		fields=["name", "item_name", "stock_uom"],
	)
	
	result = []
	for item in items:
		qty = get_stock_balance(
			item.get("name"),
			warehouse,
			posting_date,
			posting_time
		)
		
		if ignore_empty_stock and qty == 0:
			continue
		
		result.append({
			"item_code": item.get("name"),
			"item_name": item.get("item_name"),
			"warehouse": warehouse,
			"qty": qty,
			"stock_uom": item.get("stock_uom"),
		})
	
	return result


@frappe.whitelist()
def get_stock_balance_for(item_code, warehouse, posting_date, posting_time, batch_no=None, row=None, company=None):
	"""
	Get current stock balance for an item
	
	Args:
		item_code: Item code
		warehouse: Warehouse
		posting_date: Posting date
		posting_time: Posting time
		batch_no: Optional batch number
		row: Optional row data
		company: Company name
	
	Returns:
		Dictionary with qty, rate, serial_nos, use_serial_batch_fields
	"""
	from erpnext.stock.utils import get_stock_balance, get_valuation_rate
	from erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle import get_serial_batch_ledger
	
	qty = get_stock_balance(
		item_code,
		warehouse,
		posting_date,
		posting_time,
		batch_no=batch_no
	)
	
	rate = get_valuation_rate(
		item_code,
		warehouse,
		posting_date,
		posting_time,
		batch_no=batch_no,
		company=company
	)
	
	serial_nos = ""
	use_serial_batch_fields = 0
	
	# Check if item uses serial/batch
	item_doc = frappe.get_doc("Item", item_code)
	if item_doc.has_serial_no or item_doc.has_batch_no:
		use_serial_batch_fields = 1
	
	return {
		"qty": qty,
		"rate": rate,
		"serial_nos": serial_nos,
		"use_serial_batch_fields": use_serial_batch_fields,
	}


@frappe.whitelist()
def get_difference_account(purpose, company):
	"""
	Get the appropriate difference account based on purpose
	
	Args:
		purpose: Purpose of reconciliation (Opening Stock or Stock Reconciliation)
		company: Company name
	
	Returns:
		Account name or empty string
	"""
	account = ""
	
	if purpose == "Opening Stock":
		# For opening stock, use stock adjustment account
		account = frappe.db.get_value(
			"Company",
			company,
			"stock_adjustment_account"
		)
	elif purpose == "Stock Reconciliation":
		# For stock reconciliation, use stock adjustment account
		account = frappe.db.get_value(
			"Company",
			company,
			"stock_adjustment_account"
		)
	
	return account or ""