# Copyright (c) 2025, nei and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class PackageInspection(Document):
	pass


@frappe.whitelist()
def get_package_details_by_barcode(barcode):
	"""
	Get package details from Batch Barcode Tracker by barcode.
	Returns: Product Code, Product Name, Batch Number, Date of Manufacture, Warehouse Location
	"""
	try:
		# Get Batch Barcode Tracker record by barcode (name field is the barcode)
		barcode_tracker = frappe.get_doc("Batch Barcode Tracker", barcode)
		
		if not barcode_tracker:
			return None
		
		# Get item details
		item_code = barcode_tracker.item_code
		item_doc = frappe.get_doc("Item", item_code) if item_code else None
		
		# Get batch details if batch exists
		batch_no = barcode_tracker.batch or barcode_tracker.lot_no
		
		# Use posting_date from Batch Barcode Tracker as manufacture date
		# (posting_date is labeled as "Manufactured Date" in the doctype)
		manufacture_date = barcode_tracker.posting_date
		
		# Get warehouse name
		warehouse_name = None
		if barcode_tracker.warehouse:
			warehouse_name = frappe.get_value("Warehouse", barcode_tracker.warehouse, "warehouse_name") or barcode_tracker.warehouse
		
		return {
			"product_code": item_code,
			"product_name": item_doc.item_name if item_doc else None,
			"batch_number": batch_no,
			"date_of_manufacture": manufacture_date or barcode_tracker.posting_date,
			"warehouse_location": warehouse_name or barcode_tracker.warehouse,
			"warehouse_code": barcode_tracker.warehouse,
			"qty": barcode_tracker.qty,
			"uom": barcode_tracker.uom,
			"sold": barcode_tracker.sold,
			"barcode": barcode_tracker.barcode
		}
		
	except frappe.DoesNotExistError:
		return None
	except Exception as e:
		frappe.log_error(f"Error getting package details by barcode {barcode}: {str(e)}")
		return None
