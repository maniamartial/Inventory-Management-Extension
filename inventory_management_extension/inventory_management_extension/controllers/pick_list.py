import frappe
from frappe import _
from frappe.utils import flt
from frappe.model.mapper import get_mapped_doc
from inventory_management_extension.inventory_management_extension.utils import (
    validate_batch_barcode_qty_uom,
)



def before_submit(doc, method=None):
    validate_qty(doc)
    validate_custom_item_barcodes(doc)
    for item in doc.locations:
        missing_fields = []

        if not item.custom_packaging_item:
            missing_fields.append('<span style="color:purple;">Packaging Item</span>')
        if not item.custom_packing_weight or item.custom_packing_weight == 0:
            missing_fields.append('<span style="color:purple;">Packing Weight</span>')
        if not item.custom_gross_weight or item.custom_gross_weight <= 0:
            missing_fields.append('<span style="color:purple;">Gross Weight</span>')

        if missing_fields:
            frappe.throw(
                _("Missing {0} for item <b style='color:black;'>{1}</b>").format(", ".join(missing_fields), item.item_code)
            )
    


def validate_qty(doc):
    total_qty = 0
    sales_order = frappe.get_doc("Sales Order", doc.custom_sales_order)
    if not sales_order:
        frappe.throw(_("Sales Order is not linked."))

    for qty in doc.locations:
        total_qty += flt(qty.qty, 4)  # Or use 4/5 if you need more precision

    # Get picklist allowance from Selling Settings
    picklist_allowance = frappe.db.get_single_value("Selling Settings", "custom_picklist_allowance") or 0
    picklist_allowance = flt(picklist_allowance, 2)
    
    # Calculate allowed quantity: SO qty * (1 + allowance/100)
    # Example: 40% allowance means 140% of SO qty is allowed
    sales_order_qty = flt(sales_order.total_qty, 4)
    allowed_qty = sales_order_qty * (1 + picklist_allowance / 100)
    allowed_qty = flt(allowed_qty, 4)

    if flt(total_qty, 4) > allowed_qty:
        if picklist_allowance > 0:
            frappe.throw(
                _("Total Picked quantity <b>{0}</b> cannot exceed allowed quantity <b>{1}</b> (Sales Order quantity <b>{2}</b> + {3}% allowance)").format(
                    total_qty, allowed_qty, sales_order_qty, picklist_allowance
                )
            )
        else:
            frappe.throw(
                _("Total Picked quantity <b>{0}</b> cannot exceed Sales Order quantity <b>{1}</b>").format(
                    total_qty, sales_order_qty
                )
            )
        
def before_save(doc, method=None):
    validate_qty(doc)
    validate_custom_item_barcodes(doc)
    calculate_package_weight(doc)


def validate_custom_item_barcodes(doc):
    """Ensure picked barcodes match pack qty/UOM (whole pack sell)."""
    for row in doc.get("custom_items") or []:
        if not row.barcode:
            continue
        validate_batch_barcode_qty_uom(
            barcode=row.barcode,
            item_code=row.item_code,
            qty=row.qty,
            uom=row.uom,
            stock_uom=row.stock_uom,
            conversion_factor=row.conversion_factor,
            stock_qty=row.stock_qty,
            context=f"Pick List pack {row.idx} ({row.item_code})",
            require_full_pack=True,
        )
    
def calculate_package_weight(doc):
    # total_weight = 0
    for item in doc.locations:
        item.custom_packaging_item = doc.custom_packaging_item
        item.custom_packing_weight = doc.custom_packing_weight
        item.custom_packaging_itemuom = doc.custom_packaging_itemuom
        item.custom_cubic = doc.custom_cubic * item.custom_barcode_no
        item.custom_gross_weight = (doc.custom_packing_weight * item.custom_barcode_no) + item.qty


@frappe.whitelist()
def picklist_to_invoice(picklist_name):
    picklist = frappe.get_doc("Pick List", picklist_name)

    if not picklist.custom_sales_order:
        frappe.throw(_("No Sales Order linked to Pick List"))

    sales_order = frappe.get_doc("Sales Order", picklist.custom_sales_order)

    invoice = frappe.new_doc("Sales Invoice")
    invoice.customer = sales_order.customer
    invoice.due_date = frappe.utils.nowdate()
    invoice.custom_sales_order = sales_order.name
    invoice.set_posting_time = 1
    invoice.currency = sales_order.currency
    invoice.conversion_rate = sales_order.conversion_rate
    invoice.selling_price_list = sales_order.selling_price_list
    invoice.price_list_currency = sales_order.price_list_currency
    invoice.plc_conversion_rate = sales_order.plc_conversion_rate

    for loc in picklist.locations:
        so_item = next((item for item in sales_order.items if item.item_code == loc.item_code), None)
        if not so_item:
            continue

        invoice.append("items", {
            "item_code": loc.item_code,
            "qty": loc.qty,
            "uom": so_item.uom,
            "stock_uom": so_item.stock_uom,
            "warehouse": loc.warehouse,
            "rate": so_item.rate,
            "base_rate": so_item.base_rate,
            "batch_no": loc.batch_no,
            "sales_order": sales_order.name,
            "sales_order_item": so_item.name,
            "custom_barcode_no": loc.custom_barcode_no,
            "custom_package_item": loc.custom_packaging_item,
            "custom_package_weight": loc.custom_packing_weight,
            "custom_gross_weight": loc.custom_gross_weight,
            "custom_cubic": loc.custom_cubic,
            "custom_packaging_itemuom": loc.custom_packaging_itemuom,
        })

    invoice.flags.ignore_permissions = True
    invoice.insert()
    return invoice.name


@frappe.whitelist()
def get_used_barcodes_in_submitted_picklists():
    """
    Get list of barcodes that are already used in submitted Pick Lists.
    Returns a list of barcode names (Batch Barcode Tracker names).
    """
    # Get all barcodes from Pick List Extension (custom_items) 
    # where parent Pick List is submitted (docstatus = 1)
    used_barcodes = frappe.db.sql("""
        SELECT DISTINCT ple.barcode
        FROM `tabPick List Extension` ple
        INNER JOIN `tabPick List` pl ON ple.parent = pl.name
        WHERE pl.docstatus = 1 
        AND ple.barcode IS NOT NULL
        AND ple.barcode != ''
    """, as_list=True)
    
    # Flatten the list of tuples to a simple list
    return [barcode[0] for barcode in used_barcodes if barcode[0]]


@frappe.whitelist()
def get_barcode_query(doctype, txt, searchfield, start, page_len, filters):
    """
    Custom query method for barcode field in Pick List Extension.
    Excludes barcodes already used in submitted Pick Lists.
    """
    # Get the filters from the client
    item_code = filters.get('item_code') if filters else None
    batch = filters.get('batch') if filters else None
    sold = filters.get('sold', 0) if filters else 0
    exclude_barcodes = filters.get('exclude_barcodes', []) if filters else []
    
    # Build the base query
    conditions = []
    values = []
    
    # Item code filter
    if item_code:
        conditions.append("bbt.item_code = %s")
        values.append(item_code)
    
    # Batch filter
    if batch:
        conditions.append("bbt.batch = %s")
        values.append(batch)
    
    # Sold filter
    conditions.append("bbt.sold = %s")
    values.append(sold)
    
    # Text search
    if txt:
        conditions.append("(bbt.name LIKE %s OR bbt.barcode LIKE %s)")
        values.extend([f"%{txt}%", f"%{txt}%"])
    
    # Get barcodes already used in submitted Pick Lists
    used_barcodes = frappe.db.sql("""
        SELECT DISTINCT ple.barcode
        FROM `tabPick List Extension` ple
        INNER JOIN `tabPick List` pl ON ple.parent = pl.name
        WHERE pl.docstatus = 1 
        AND ple.barcode IS NOT NULL
        AND ple.barcode != ''
    """, as_list=True)
    
    used_barcode_list = [barcode[0] for barcode in used_barcodes if barcode[0]]
    
    # Combine with exclude_barcodes from client
    all_excluded = list(set(used_barcode_list + (exclude_barcodes if exclude_barcodes else [])))
    
    # Exclude used barcodes
    if all_excluded:
        # Use tuple for NOT IN clause
        placeholders = ','.join(['%s'] * len(all_excluded))
        conditions.append(f"bbt.name NOT IN ({placeholders})")
        values.extend(all_excluded)
    
    # Build the final query
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    query = f"""
        SELECT DISTINCT bbt.name, bbt.barcode, bbt.item_code, bbt.qty
        FROM `tabBatch Barcode Tracker` bbt
        WHERE {where_clause}
        ORDER BY bbt.name
        LIMIT %s OFFSET %s
    """
    
    values.extend([page_len, start])
    
    results = frappe.db.sql(query, tuple(values), as_dict=True)
    
    # Format results for Frappe's Link field
    return [[r.name, r.barcode or r.name] for r in results]
