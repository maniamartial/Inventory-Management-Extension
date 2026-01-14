import frappe
import random
import barcode
from barcode.writer import ImageWriter
from inventory_management_extension.inventory_management_extension.utils import create_barcode_tracker, mark_barcode_as_sold

def calculate_ean13_check_digit(ean12):
    """
    Calculate the EAN-13 check digit for a 12-digit string.
    """
    odd_sum = sum(int(ean12[i]) for i in range(0, 12, 2))
    even_sum = sum(int(ean12[i]) for i in range(1, 12, 2))
    total = odd_sum + 3 * even_sum
    check_digit = (10 - (total % 10)) % 10
    return check_digit

def generate_ean13():
    """Generate a valid random EAN-13 barcode as a string."""
    ean12 = ''.join(str(random.randint(0, 9)) for _ in range(12))
    check_digit = calculate_ean13_check_digit(ean12)
    return ean12 + str(check_digit)


def before_save(doc, method):
    if doc.stock_entry_type in ["Manufacture", "Material Receipt", "Repack", "Material Transfer"]:
        for item in doc.items:
            # Skip if item doesn't need batch
            if not valiadte_item_has_batch(item.item_code):
                continue

            # Manufacture: only generate for finished item
            if doc.stock_entry_type == "Manufacture" and not item.is_finished_item:
                continue

            # Repack: only generate for items being added (target warehouse exists)
            if doc.stock_entry_type == "Repack" and not item.t_warehouse:
                continue

            # Material Transfer: only generate for target items (items with t_warehouse)
            if doc.stock_entry_type == "Material Transfer" and not item.t_warehouse:
                continue

            # Material Receipt: all items with batch requirement are valid

            # Generate and set barcode if not already present
            if not item.custom_transaction_barcode:
                item.custom_transaction_barcode = generate_ean13()
                update_barcode_on_item(item.item_code, item.custom_transaction_barcode)

        # After assigning barcodes, generate batches
        generate_batch_no(doc)

                
def update_barcode_on_item(item_code, barcode):
    item_doc = frappe.get_doc("Item", item_code)
    item_doc.append("barcodes", {
        "barcode": barcode
    })
    item_doc.save()
    

def on_submit(doc, method):
    is_lot=False
    
    # Handle Manufacture: mark source barcodes as sold, create new tracker for finished items
    if doc.stock_entry_type == "Manufacture":
        handle_manufacture(doc)
    
    # Handle Material Receipt (existing logic - only create new trackers)
    elif doc.stock_entry_type == "Material Receipt":
        for item in doc.items:
            if item.custom_transaction_barcode:
                create_barcode_tracker(
                    item.item_code, 
                    item.custom_transaction_barcode, 
                    item.batch_no, 
                    item.qty,
                    item.t_warehouse, 
                    item.custom_barcode_image, 
                    reference_document_type=doc.doctype,
                    reference_document_name=doc.name
                )
                update_serial_and_batch(doc, item)
    
    # Handle Repack: mark source barcodes as sold, create new tracker for target
    elif doc.stock_entry_type == "Repack":
        handle_repack(doc)
    
    # Handle Material Transfer: mark source barcodes as sold, create new tracker for target
    elif doc.stock_entry_type == "Material Transfer":
        handle_material_transfer(doc)
    
    # Handle Material Issue: mark selected barcodes as sold, no new tracker
    elif doc.stock_entry_type == "Material Issue":
        handle_material_issue(doc)
    
    # Handle other stock entry types based on source/target warehouse
    else:
        handle_other_stock_entry_types(doc)


def handle_manufacture(doc):
    """
    Handle Manufacture:
    - Mark selected batch barcodes (raw materials/source items) as sold (consumed)
    - Create new batch barcode tracker for finished items (target items)
    """
    is_lot = False
    if doc.custom_create_lot == 1:
        is_lot = True
    
    for item in doc.items:
        # Mark source barcodes as sold if selected (raw materials being consumed)
        if item.custom_batch_barcode and item.s_warehouse:
            mark_barcode_as_sold(item.custom_batch_barcode, doc.doctype, doc.name)
        
        # Create new tracker for finished items (target items with t_warehouse)
        if item.is_finished_item and item.t_warehouse and item.custom_transaction_barcode and item.batch_no:
            create_barcode_tracker(
                item.item_code, 
                item.custom_transaction_barcode, 
                item.batch_no, 
                item.qty,
                item.t_warehouse, 
                item.custom_barcode_image,
                is_lot=is_lot,
                reference_document_type=doc.doctype,
                reference_document_name=doc.name
            )
            update_serial_and_batch(doc, item)


def handle_repack(doc):
    """
    Handle Repack:
    - Mark selected batch barcodes (source) as sold
    - Create new batch barcode tracker for target items (finished goods)
    """
    is_lot = False
    if doc.custom_create_lot == 1:
        is_lot = True
    
    for item in doc.items:
        # Mark source barcodes as sold if selected (source items)
        if item.custom_batch_barcode and item.s_warehouse:
            mark_barcode_as_sold(item.custom_batch_barcode, doc.doctype, doc.name)
        
        # Create new tracker for target items (finished goods with t_warehouse)
        if item.t_warehouse and item.custom_transaction_barcode and item.batch_no:
            create_barcode_tracker(
                item.item_code, 
                item.custom_transaction_barcode, 
                item.batch_no, 
                item.qty,
                item.t_warehouse, 
                item.custom_barcode_image,
                is_lot=is_lot,
                reference_document_type=doc.doctype,
                reference_document_name=doc.name
            )
            update_serial_and_batch(doc, item)


def handle_material_transfer(doc):
    """
    Handle Material Transfer:
    - Mark selected batch barcodes (source) as sold
    - Create new batch barcode tracker for target items
    """
    for item in doc.items:
        # Mark source barcodes as sold if selected
        if item.custom_batch_barcode and item.s_warehouse:
            mark_barcode_as_sold(item.custom_batch_barcode, doc.doctype, doc.name)
        
        # Create new tracker for target items
        if item.t_warehouse and item.custom_transaction_barcode and item.batch_no:
            create_barcode_tracker(
                item.item_code, 
                item.custom_transaction_barcode, 
                item.batch_no, 
                item.qty,
                item.t_warehouse, 
                item.custom_barcode_image,
                reference_document_type=doc.doctype,
                reference_document_name=doc.name
            )
            update_serial_and_batch(doc, item)


def handle_material_issue(doc):
    """
    Handle Material Issue:
    - Mark selected batch barcodes as sold (items are gone, no new tracker)
    """
    for item in doc.items:
        if item.custom_batch_barcode:
            mark_barcode_as_sold(item.custom_batch_barcode, doc.doctype, doc.name)


def handle_other_stock_entry_types(doc):
    """
    Handle other stock entry types based on source/target warehouse logic:
    - If only s_warehouse (stock out): mark barcodes as sold
    - If only t_warehouse (stock in): create new tracker
    - If both (stock out and in): mark source as sold, create new tracker for target
    """
    for item in doc.items:
        has_source = bool(item.s_warehouse)
        has_target = bool(item.t_warehouse)
        
        # Stock out only: mark barcodes as sold
        if has_source and not has_target:
            if item.custom_batch_barcode:
                mark_barcode_as_sold(item.custom_batch_barcode, doc.doctype, doc.name)
        
        # Stock in only: create new tracker
        elif has_target and not has_source:
            if item.custom_transaction_barcode and item.batch_no:
                create_barcode_tracker(
                    item.item_code, 
                    item.custom_transaction_barcode, 
                    item.batch_no, 
                    item.qty,
                    item.t_warehouse, 
                    item.custom_barcode_image,
                    reference_document_type=doc.doctype,
                    reference_document_name=doc.name
                )
                update_serial_and_batch(doc, item)
        
        # Both source and target (like Repack): mark source as sold, create new tracker
        elif has_source and has_target:
            # Mark source barcode as sold if selected
            if item.custom_batch_barcode:
                mark_barcode_as_sold(item.custom_batch_barcode, doc.doctype, doc.name)
            
            # Create new tracker for target
            if item.custom_transaction_barcode and item.batch_no:
                create_barcode_tracker(
                    item.item_code, 
                    item.custom_transaction_barcode, 
                    item.batch_no, 
                    item.qty,
                    item.t_warehouse, 
                    item.custom_barcode_image,
                    reference_document_type=doc.doctype,
                    reference_document_name=doc.name
                )
                update_serial_and_batch(doc, item)
                
                
def update_serial_and_batch(doc, item):
    entry = frappe.get_value(
        "Serial and Batch Bundle",
        {"voucher_no": doc.name, "voucher_type": doc.doctype, "item_code": item.item_code},
        "name"
    )
    if entry:
        bundle_doc = frappe.get_doc("Serial and Batch Bundle", entry)

        # Update the custom_barcode field in the entries child table
        for row in bundle_doc.entries:
            row.custom_barcode = item.custom_transaction_barcode

        bundle_doc.save(ignore_permissions=True)


def latest_batch(batch_prefix):
    latest_batch = frappe.db.sql(
        """SELECT batch_id FROM `tabBatch`
        WHERE batch_id LIKE %s
        ORDER BY creation DESC LIMIT 1""",
        (batch_prefix + "%",), as_dict=True
    )

    if latest_batch:
        last_number = int(latest_batch[0].batch_id.split("-")[-1])
        new_number = f"{last_number + 1:05}"
    else:
        new_number = "0001"

    new_batch_no = f"{batch_prefix}{new_number}"
    return new_batch_no

def create_batch(batch_no, item_code):
    batch = frappe.new_doc("Batch")
    batch.batch_id = batch_no
    batch.item = item_code
    batch.insert()
    return batch


def generate_year_prefixed_batch():
    """
    Generate batch number with year prefix in format [YY]-Series
    Example: 24-00001, 24-00002, 25-00001
    """
    from datetime import datetime
    
    # Get current year as 2-digit string
    current_year = datetime.now().strftime("%y")
    year_prefix = f"{current_year}-"
    
    # Find the latest batch for current year
    latest_batch = frappe.db.sql(
        """SELECT batch_id FROM `tabBatch`
        WHERE batch_id LIKE %s
        ORDER BY creation DESC LIMIT 1""",
        (year_prefix + "%",), as_dict=True
    )
    
    if latest_batch:
        # Extract the series number from the latest batch
        try:
            series_part = latest_batch[0].batch_id.split("-")[-1]
            next_series = int(series_part) + 1
        except (ValueError, IndexError):
            # If parsing fails, start from 1
            next_series = 1
    else:
        # No batch exists for current year, start from 1
        next_series = 1
    
    # Format series as 5-digit number with leading zeros
    series_formatted = f"{next_series:05d}"
    
    # Combine year prefix with series
    new_batch_id = f"{year_prefix}{series_formatted}"
    
    return new_batch_id

def generate_code128():
    """
    Generate a valid random Code 128 barcode as a string and save it as an image.
    """
    random_number = ''.join(str(random.randint(0, 9)) for _ in range(12))
    
    code128 = barcode.get_barcode_class('code128')
    
    barcode_instance = code128(random_number, writer=ImageWriter())
    
    filename = barcode_instance.save('code128_barcode')
    
    return random_number, filename

def generate_batch_no(doc):
    item_batch_map = {}
    
    for item in doc.items:
        if frappe.get_doc("Item", item.item_code).has_batch_no == 1:
            if item.batch_no: 
                continue
            item.use_serial_batch_fields = 1
            if doc.doctype=="Stock Entry" and doc.stock_entry_type == "Manufacture" and not item.is_finished_item:
                continue
            
            if item.item_code in item_batch_map:
                item.batch_no = item_batch_map[item.item_code]
                continue
            
            # Generate batch with year prefix [YY]-Series format
            new_batch_id = generate_year_prefixed_batch()
        
            batch = frappe.get_doc({
                "doctype": "Batch",
                "batch_id": new_batch_id,
                "item": item.item_code,
                "expiry_date": item.get("expiry_date")
            })
            batch.insert(ignore_permissions=True)
        
            item.batch_no = new_batch_id
            item_batch_map[item.item_code] = new_batch_id
            
            
def valiadte_item_has_batch(item_code):
    item_doc = frappe.get_doc("Item", item_code)
    if item_doc.has_batch_no == 1:
        return True
    return False