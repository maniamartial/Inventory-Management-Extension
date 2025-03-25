import frappe
from .stock_entry import generate_batch_no, create_batch, generate_ean13, update_barcode_on_item, update_serial_and_batch, valiadte_item_has_batch

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
                update_serial_and_batch(doc, item)
    