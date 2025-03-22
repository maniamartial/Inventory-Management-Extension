import frappe
import random
import barcode
from barcode.writer import ImageWriter

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
    if doc.stock_entry_type != "Manufacture":
        return

    for item in doc.items:
        if not item.is_finished_item:
            continue

        if not item.batch_no:
            
            batch_no = generate_batch_no(item.item_code)
            item.batch_no = create_batch(batch_no, item.item_code).batch_id

        if not item.serial_no:
            item.serial_no = generate_ean13()


def generate_batch_no(item_code):
    item_doc = frappe.get_doc("Item", item_code)
    suppliers = item_doc.get("supplier_items", [])

    cert_abbreviations = []

    for supplier in suppliers:
        supplier_doc = frappe.get_doc("Supplier", supplier.supplier)
        for cert in supplier_doc.get("custom_certifications", []):
            cert_abbreviations.append(cert.abbr)

    cert_abbreviation = "".join(cert_abbreviations) if cert_abbreviations else "XXX"

    batch_prefix = f"{item_doc.custom_code}{cert_abbreviation}-{item_doc.custom_grade}-"
    new_batch_no = latest_batch(batch_prefix)
    
    return new_batch_no

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
