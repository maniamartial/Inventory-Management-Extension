
import frappe 
from frappe.utils import flt
from frappe import _
from frappe.model.document import Document
import json

def create_barcode_tracker(item_code, barcode, batch, qty):
    """
    Create a barcode tracker for the given item code, barcode, and batch.
    """
    # Check if the barcode already exists
    if frappe.db.exists("Batch Barcode Tracker", {"barcode": barcode}):
        # If it exists, update the existing record
        frappe.throw("Barcode already exists.")
        
    # Create a new barcode tracker record
    barcode_tracker = frappe.get_doc({
        "doctype": "Batch Barcode Tracker",
        "item_code": item_code,
        "barcode": barcode,
        "batch": batch,
        "qty": qty,
        
    })
    barcode_tracker.insert()
    barcode_tracker.submit()
    return barcode_tracker

@frappe.whitelist()
def get_total_qty_from_barcodes():
    barcode_data = frappe.form_dict.get("barcode")
    if not barcode_data:
        return 0  

    try:
        # Parse the JSON string into Python objects
        barcode_list = frappe.parse_json(barcode_data)

        # Extract barcodes from the list of dictionaries
        barcodes = [entry.get("barcodes") for entry in barcode_list if entry.get("barcodes")]
        
        if not barcodes:
            return 0  

        batch_data = frappe.get_all(
            "Batch Barcode Tracker",
            filters={"barcode": ["in", barcodes]},
            fields=["barcode", "qty"]
        )
        total_qty = sum(flt(entry.get("qty", 0)) for entry in batch_data)
        return total_qty
        
    except Exception as e:
        frappe.log_error(f"Error in get_total_qty_from_barcodes: {str(e)}")
        frappe.throw("Failed to process barcodes. Please check the format and try again.")
        
import json
from frappe.utils import cstr

def update_batch_tracker(doc):
    selected_barcodes = [entry.barcodes for entry in doc.custom_batch_barcode]
    for m in selected_barcodes:
        frappe.db.set_value("Batch Barcode Tracker", m, "sold", 1)
    