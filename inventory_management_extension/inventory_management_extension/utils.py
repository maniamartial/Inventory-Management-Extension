
import frappe 
from frappe.utils import flt
from frappe import _
from frappe.model.document import Document
import json
from frappe.utils import cstr
from barcode import Code128
from barcode.writer import ImageWriter

def create_barcode_tracker(item_code, barcode, batch, qty):
    """
    Create a barcode tracker for the given item code, barcode, and batch.
    """
    image = generate_image_for_barcode(barcode)  # Get the file URL
    # frappe.throw(str(image))  # Debugging line to check the image URL
    # if not image:
    #     frappe.throw("Failed to generate barcode image.")

    # Check if the barcode already exists
    if frappe.db.exists("Batch Barcode Tracker", {"barcode": barcode}):
        frappe.throw("Barcode already exists.")
        
    # Create a new barcode tracker record
    barcode_tracker = frappe.get_doc({
        "doctype": "Batch Barcode Tracker",
        "item_code": item_code,
        "barcode": barcode,
        "batch": batch,
        "qty": qty,
        "barcode_image": image,  # Save the file URL here
    })
    barcode_tracker.insert(ignore_permissions=True)  # Ensure it inserts]
    barcode_tracker.submit() # Reload the document to get the latest data
    frappe.db.commit()  # Ensure database commit

    return barcode_tracker


@frappe.whitelist()
def get_total_qty_from_barcodes():
    barcode_data = frappe.form_dict.get("barcode")
    if not barcode_data:
        return 0  

    try:
        barcode_list = frappe.parse_json(barcode_data)

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
        

def update_batch_tracker(doc):
    selected_barcodes = [entry.barcodes for entry in doc.custom_batch_barcode]
    for m in selected_barcodes:
        frappe.db.set_value("Batch Barcode Tracker", m, "sold", 1)
    
    
# Copyright (c) 2024, Your Name and contributors
# License: MIT. See LICENSE

import frappe
from frappe.utils import flt

@frappe.whitelist()
def split_purchase_receipt_items():
    """Split items in Purchase Receipt based on custom_split_no"""
    purchase_receipt = frappe.form_dict.get("purchase_receipt")
    pr_doc = frappe.get_doc("Purchase Receipt", purchase_receipt)
    
    items_to_process = [item for item in pr_doc.items]
    
    for item in items_to_process:
        split_no = item.custom_split_no or 1  
        if split_no > 1 and item.qty:
            
            new_items = []
            for i in range(split_no):
                new_item = {
                    'item_code': item.item_code,
                    'qty': item.qty,
                    'uom': item.uom,
                    'stock_uom': item.stock_uom,
                    'conversion_factor': item.conversion_factor,
                    'stock_qty': item.stock_qty,
                    'rate': item.rate,
                    'amount': item.amount,
                    'warehouse': item.warehouse,
                    'batch_no': item.batch_no,
                    'serial_no': item.serial_no,
                    'expense_account': item.expense_account,
                    'cost_center': item.cost_center,
                    'custom_split_no': 1 
                }
                new_items.append(new_item)
            
            # Remove the original item and add the new split items
            pr_doc.remove(item)
            for new_item in new_items:
                pr_doc.append('items', new_item)
    
    # Save the updated purchase receipt
    pr_doc.save()
    frappe.db.commit()
    
    return pr_doc.name

@frappe.whitelist()
def split_stock_entry_items():
    """Split items in Purchase Receipt based on custom_split_no"""
    stock_entry = frappe.form_dict.get("stock_entry")
    pr_doc = frappe.get_doc("Stock Entry", stock_entry)
    
    items_to_process = [item for item in pr_doc.items]
    
    for item in items_to_process:
        split_no = item.custom_split_no or 1  
        if split_no > 1 and item.qty:
            new_items = []
            for i in range(split_no):
                new_item = {
                    'item_code': item.item_code,
                    'qty': item.qty,
                    'uom': item.uom,
                    'stock_uom': item.stock_uom,
                    'conversion_factor': item.conversion_factor,
                    'rate': item.basic_rate,
                    'basic_amount': item.basic_amount,
                    'amount': item.amount,
                    "s_warehouse": item.s_warehouse,
                    "t_warehouse": item.t_warehouse,
                    'batch_no': item.batch_no,
                    'serial_no': item.serial_no,
                    'expense_account': item.expense_account,
                    'cost_center': item.cost_center,
                    'custom_split_no': 1 
                }
                new_items.append(new_item)
            
            pr_doc.remove(item)
            for new_item in new_items:
                pr_doc.append('items', new_item)
    pr_doc.save()
    frappe.db.commit()
    
    return pr_doc.name

import os
import frappe
from barcode import Code128
from barcode.writer import ImageWriter
from frappe.utils.file_manager import save_file
import os
import re

def sanitize_filename(filename):
    """
    Remove special characters and replace spaces with underscores.
    """
    filename = re.sub(r'[^\w\s.-]', '', filename)  # Remove special characters
    filename = filename.replace(" ", "_")  # Replace spaces with underscores
    return filename

def generate_image_for_barcode(barcode):
    """
    Generate a barcode image and save it in Frappe's file system.
    """
    try:
        # Sanitize filename to remove spaces and special characters
        sanitized_filename = sanitize_filename(barcode)
        
        # Define the file path (change to `public/files/` if you want public access)
        file_path = frappe.get_site_path(f"private/files/{sanitized_filename}.png")

        # Create a Code128 barcode object
        code = Code128(barcode, writer=ImageWriter())

        # Save the barcode image
        code.save(file_path.replace(".png", ""))  # barcode lib auto-appends .png

        # Save file in Frappe's file system and link to File document
        with open(file_path, "rb") as f:
            file_doc = save_file(f"{sanitized_filename}.png", f.read(), "Batch Barcode Tracker", barcode, is_private=1)
        return file_doc.file_url  # Return Frappe file URL
    except Exception as e:
        frappe.log_error(f"Error generating barcode image: {str(e)}")
        return None
    
    
@frappe.whitelist()
def get_conversion_factor():
    item_code= frappe.form_dict.get("item_code")
    uom= frappe.form_dict.get("uom")
    """
    Fetches the conversion factor for the given item_code and UOM.
    """
    conversion_factor = frappe.db.get_value(
        "UOM Conversion Detail",
        {"parent": item_code, "uom": uom},
        "conversion_factor"
    )
    
    if conversion_factor:
        return {"conversion_factor": conversion_factor}
    else:
        return {"error": f"Conversion factor not found for {uom} in {item_code}"}