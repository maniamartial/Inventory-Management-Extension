

import frappe
import random

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
    if doc.stock_entry_type == "Manufacture":
        for item in doc.items:
            batch = generate_batch_no(item.item_code)
            item.batch_no = batch
            if item.is_finished_item==1:
                serial_number = generate_ean13()
                frappe.msgprint(f"Generated Serial No (EAN-13): {serial_number}")

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
