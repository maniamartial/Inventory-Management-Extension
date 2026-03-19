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

	def before_submit(self):
		"""Ensure for each (batch, warehouse) all unsold Batch Barcode Trackers are in items or in missing_batch_barcodes."""
		self.validate_all_batch_barcodes_entered()

	def validate_all_batch_barcodes_entered(self):
		"""
		Before submit:
		1) Every row in new_barcodes must have batch_barcode_tracker_created = 1 (Material Receipt submitted).
		2) Every row in missing_batch_barcodes must have batch_barcode_tracker_update = 1 (Material Issue submitted).
		3) For each (batch, warehouse) with barcodes in items: any tracker (sold=0) not in items must be in
		   missing_batch_barcodes with batch_barcode_tracker_update = 1.
		"""
		# 1) New barcodes: all must be ticked (tracker created via Material Receipt)
		for row in (self.new_barcodes or []):
			if not row.barcode:
				continue
			if not cint(row.get("batch_barcode_tracker_created")):
				frappe.throw(
					_("New Barcodes: row with barcode '{0}' must have Batch Barcode Tracker Created. Create Stock Entry (Material Receipt) and submit it first.").format(row.barcode),
					title=_("New barcodes not received"),
				)
		# 2) Missing batch barcodes: rows not in items must be ticked (Material Issue created and submitted)
		barcode_in_items = {item.batch_barcode for item in (self.items or []) if item.batch_barcode}
		for row in (self.missing_batch_barcodes or []):
			if not row.barcode:
				continue
			if row.barcode in barcode_in_items:
				continue  # already in items, no tick needed
			if not cint(row.get("batch_barcode_tracker_update")):
				frappe.throw(
					_("Missing Batch Barcodes: row with barcode '{0}' must have Batch Barcode Tracker Update. Create Stock Entry (Material Issue) and submit it first, or add to Items via 'Add Missing to Items'.").format(row.barcode),
					title=_("Missing barcodes not issued"),
				)
		# 3) For (batch, warehouse) in items: any tracker not in items must be in missing with tick
		if not self.items:
			return
		batch_wh_with_barcode = set()
		barcode_in_items = set()
		for item in self.items:
			if item.batch_barcode and item.batch_no and item.warehouse:
				batch_wh_with_barcode.add((item.batch_no, item.warehouse))
				barcode_in_items.add(item.batch_barcode)
		if not batch_wh_with_barcode:
			return
		missing_ticked = {row.barcode for row in (self.missing_batch_barcodes or []) if row.barcode and cint(row.get("batch_barcode_tracker_update"))}
		for (batch_no, warehouse) in batch_wh_with_barcode:
			all_trackers = frappe.get_all(
				"Batch Barcode Tracker",
				filters={"batch": batch_no, "warehouse": warehouse, "sold": 0},
				pluck="name",
			)
			in_items = {item.batch_barcode for item in self.items if item.batch_no == batch_no and item.warehouse == warehouse}
			for t in all_trackers:
				if t not in in_items and t not in missing_ticked:
					frappe.throw(
						_("Batch {0}, Warehouse {1}: barcode tracker {2} is not in Items and not marked as issued. Add to Items or create Stock Entry (Material Issue) and submit.").format(batch_no, warehouse, t),
						title=_("Missing batch barcodes"),
					)

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


@frappe.whitelist()
def get_missing_batch_barcodes(doc):
	"""
	For the given Batch Barcode Reconciliation doc, find all Batch Barcode Trackers
	(batch + warehouse, sold=0) that are not in items. Return and optionally
	populate missing_batch_barcodes table. doc can be dict or JSON string.
	"""
	if isinstance(doc, str):
		doc = frappe.parse_json(doc)
	items = doc.get("items") or []
	batch_wh_with_barcode = set()
	barcode_in_items = set()
	for item in items:
		if item.get("batch_barcode") and item.get("batch_no") and item.get("warehouse"):
			batch_wh_with_barcode.add((item.get("batch_no"), item.get("warehouse")))
			barcode_in_items.add(item.get("batch_barcode"))
	missing_rows = []
	for (batch_no, warehouse) in batch_wh_with_barcode:
		all_trackers = frappe.get_all(
			"Batch Barcode Tracker",
			filters={"batch": batch_no, "warehouse": warehouse, "sold": 0},
			fields=["name", "barcode", "qty", "batch", "warehouse"],
		)
		in_items = {
			i.get("batch_barcode") for i in items
			if i.get("batch_no") == batch_no and i.get("warehouse") == warehouse
		}
		for t in all_trackers:
			if t["name"] not in in_items:
				missing_rows.append({
					"barcode": t["name"],
					"qty": flt(t.get("qty")),
					"batch": t.get("batch"),
					"warehouse": t.get("warehouse"),
				})
	return missing_rows


@frappe.whitelist()
def add_missing_batch_barcodes_to_items(doc_name):
	"""
	From the Batch Barcode Reconciliation's missing_batch_barcodes table, add each
	row as an item (fetch tracker details and append to items). Call after
	Fetch Missing Batch Barcodes has populated missing_batch_barcodes.
	"""
	doc = frappe.get_doc("Batch Barcode Reconciliation", doc_name)
	if not doc.missing_batch_barcodes:
		return {"added": 0, "message": _("No rows in Missing Batch Barcodes.")}
	existing_barcodes = {item.batch_barcode for item in (doc.items or []) if item.batch_barcode}
	added = 0
	for row in doc.missing_batch_barcodes:
		if not row.barcode or row.barcode in existing_barcodes:
			continue
		tracker = frappe.db.get_value(
			"Batch Barcode Tracker",
			row.barcode,
			["item_code", "barcode", "warehouse", "batch", "qty", "uom"],
			as_dict=True,
		)
		if not tracker:
			continue
		doc.append("items", {
			"item_code": tracker.item_code,
			"warehouse": row.warehouse or tracker.warehouse,
			"batch_no": tracker.batch,
			"batch_barcode": row.barcode,
			"barcode": tracker.barcode,
			"qty": flt(row.qty) or flt(tracker.qty),
			"stock_uom": tracker.uom,
			"use_serial_batch_fields": 1,
		})
		existing_barcodes.add(row.barcode)
		added += 1
	doc.save(ignore_permissions=True)
	return {"added": added, "message": _("Added {0} missing barcode(s) to Items.").format(added)}


@frappe.whitelist()
def create_material_receipt_from_new_barcodes(doc_name):
	"""
	Create a Stock Entry of type Material Receipt from the new_barcodes table.
	Each row should have barcode, item_code, qty, warehouse (batch optional).
	"""
	doc = frappe.get_doc("Batch Barcode Reconciliation", doc_name)
	if not doc.new_barcodes:
		frappe.throw(_("No rows in New Barcodes. Scan unknown barcodes first."))
	company = doc.company
	posting_date = doc.posting_date or frappe.utils.getdate()
	posting_time = doc.posting_time or frappe.utils.get_time()
	items = []
	for row in doc.new_barcodes:
		if not row.barcode or not row.qty:
			continue
		item_code = row.get("item_code")
		if not item_code:
			frappe.throw(_("Row with barcode '{0}' has no Item Code. Please set Item Code in New Barcodes.").format(row.barcode))
		warehouse = row.get("warehouse") or doc.set_warehouse
		if not warehouse:
			frappe.throw(_("Set Default Warehouse or warehouse on each New Barcode row."))
		items.append({
			"item_code": item_code,
			"qty": flt(row.qty),
			"t_warehouse": warehouse,
			"batch_no": row.get("batch"),
			"custom_transaction_barcode": row.barcode,
			"use_serial_batch_fields": 1,
		})
	if not items:
		frappe.throw(_("No valid rows in New Barcodes."))
	ste = frappe.get_doc({
		"doctype": "Stock Entry",
		"stock_entry_type": "Material Receipt",
		"company": company,
		"posting_date": posting_date,
		"posting_time": posting_time,
		"items": items,
	})
	ste.insert(ignore_permissions=True)
	return {"stock_entry": ste.name, "message": _("Stock Entry {0} created.").format(ste.name)}


@frappe.whitelist()
def create_material_issue_from_missing_barcodes(doc_name):
	"""
	Create a Stock Entry of type Material Issue from the missing_batch_barcodes table.
	Each row is a Batch Barcode Tracker that is physically missing; issuing marks it sold.
	On submit of that Stock Entry, missing_batch_barcodes rows will be ticked (batch_barcode_tracker_update).
	"""
	doc = frappe.get_doc("Batch Barcode Reconciliation", doc_name)
	if not doc.missing_batch_barcodes:
		frappe.throw(_("No rows in Missing Batch Barcodes. Use 'Fetch Missing Batch Barcodes' first."))
	company = doc.company
	posting_date = doc.posting_date or frappe.utils.getdate()
	posting_time = doc.posting_time or frappe.utils.get_time()
	items = []
	barcode_list = []
	for row in doc.missing_batch_barcodes:
		if not row.barcode:
			continue
		tracker = frappe.db.get_value(
			"Batch Barcode Tracker",
			row.barcode,
			["item_code", "batch", "warehouse", "qty", "uom"],
			as_dict=True,
		)
		if not tracker:
			continue
		items.append({
			"item_code": tracker.item_code,
			"qty": flt(row.qty) or flt(tracker.qty),
			"s_warehouse": row.warehouse or tracker.warehouse,
			"batch_no": tracker.batch,
			"custom_batch_barcode": row.barcode,
			"use_serial_batch_fields": 1,
		})
		barcode_list.append(row.barcode)
	if not items:
		frappe.throw(_("No valid rows in Missing Batch Barcodes."))
	# Build Stock Entry dict so custom fields are always saved if they exist (hasattr can be False on new doc)
	ste_dict = {
		"doctype": "Stock Entry",
		"stock_entry_type": "Material Issue",
		"company": company,
		"posting_date": posting_date,
		"posting_time": posting_time,
		"items": items,
	}
	if frappe.db.exists("Custom Field", {"dt": "Stock Entry", "fieldname": "custom_batch_barcode_reconciliation"}):
		ste_dict["custom_batch_barcode_reconciliation"] = doc_name
		ste_dict["custom_missing_barcode_list"] = frappe.as_json(barcode_list)
	ste = frappe.get_doc(ste_dict)
	ste.insert(ignore_permissions=True)
	return {"stock_entry": ste.name, "message": _("Stock Entry {0} created. Submit it to mark barcodes as issued and tick Missing Batch Barcodes.").format(ste.name)}