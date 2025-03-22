import frappe
from .stock_entry import generate_batch_no, create_batch, generate_ean13

def before_save(doc, method=None):
    for item in doc.items:

        # if not item.batch_no:
            
        #     batch_no = generate_batch_no(item.item_code)
        #     item.batch_no = create_batch(batch_no, item.item_code).batch_id

        if not item.serial_no:
            item.serial_no = generate_ean13()
            
