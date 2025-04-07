import frappe
from .stock_entry import generate_batch_no, create_batch, generate_ean13, update_barcode_on_item, update_serial_and_batch, valiadte_item_has_batch
from inventory_management_extension.inventory_management_extension.utils import create_barcode_tracker
def before_save(doc, method=None):
    for item in doc.items:

        if not valiadte_item_has_batch(item.item_code):
            continue
        if not item.custom_transaction_barcode:
                item.custom_transaction_barcode=generate_ean13()
                update_barcode_on_item(item.item_code, item.custom_transaction_barcode)
            
    generate_batch_no(doc)
    
def on_submit(doc, method=None):
    for item in doc.items:
            if item.custom_transaction_barcode:
                create_barcode_tracker(item.item_code, item.custom_transaction_barcode, item.batch_no, item.qty, item.warehouse)
                update_serial_and_batch(doc, item)
    