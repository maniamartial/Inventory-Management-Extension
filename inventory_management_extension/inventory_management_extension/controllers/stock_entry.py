import frappe
import random
import barcode
from barcode.writer import ImageWriter
from inventory_management_extension.inventory_management_extension.utils import create_barcode_tracker

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
    if doc.stock_entry_type == "Manufacture" or doc.stock_entry_type == "Material Receipt":
    
        for item in doc.items:
            if not valiadte_item_has_batch(item.item_code):
                continue
            if not item.is_finished_item and doc.stock_entry_type == "Manufacture":
                continue

            if not item.custom_transaction_barcode:
                item.custom_transaction_barcode=generate_ean13()
                update_barcode_on_item(item.item_code, item.custom_transaction_barcode)
    generate_batch_no(doc)
                

def update_barcode_on_item(item_code, barcode):
    item_doc = frappe.get_doc("Item", item_code)
    item_doc.append("barcodes", {
        "barcode": barcode
    })
    item_doc.save()
    

def on_submit(doc, method):
    is_lot=False
    
    if doc.stock_entry_type in ["Manufacture", "Material Receipt"]:
        if doc.stock_entry_type == "Manufacture" and doc.custom_create_lot ==1:
            is_lot=True
        for item in doc.items:
            if item.custom_transaction_barcode:
                create_barcode_tracker(item.item_code, item.custom_transaction_barcode, item.batch_no, item.qty,item.t_warehouse, item.custom_barcode_image, is_lot=is_lot)
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
            
            last_batch = frappe.db.get_value(
                "Batch", 
                filters={},
                fieldname="batch_id", 
                order_by="creation DESC"
            )
        
            if last_batch and last_batch.isdigit():
                next_number = int(last_batch) + 1
            else:
                next_number = 1000
        
            new_batch_id = f"{next_number}"
        
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