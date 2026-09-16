import frappe
from frappe import _
from frappe.utils import cint, flt
from frappe.model.mapper import get_mapped_doc
from inventory_management_extension.inventory_management_extension.utils import (
    validate_batch_barcode_qty_uom,
    get_tracker_qty_snapshot,
    get_item_uom_conversions,
    resolve_pack_qty_for_uom,
    resolve_sales_order_item,
    get_uom_conversion_factor,
)



def before_submit(doc, method=None):
    ensure_item_locations(doc)
    apply_sales_order_uom(doc)
    validate_item_batch(doc)
    validate_qty(doc)
    validate_custom_item_barcodes(doc)
    # Packaging details are taken from the scanned rows, so recompute them on
    # submit as well (the last save may predate the user filling them in).
    calculate_package_weight(doc)

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
                _(
                    "Missing {0} for item <b style='color:black;'>{1}</b> in the Item Locations table. "
                    "Set the Packaging Item, Package Weight and Cubic on the Items table (or on the Pick List)."
                ).format(", ".join(missing_fields), item.item_code)
            )
    


def validate_qty(doc):
    if not doc.custom_sales_order:
        frappe.throw(_("Sales Order is not linked."))

    sales_order = frappe.get_doc("Sales Order", doc.custom_sales_order)
    if not sales_order:
        frappe.throw(_("Sales Order is not linked."))

    # Always compare in Stock UOM: a Pick List row qty can be expressed either in
    # the Stock UOM or in the Sales Order (transaction) UOM, while picked_qty /
    # stock_qty are always Stock UOM.
    total_stock_qty = 0
    for row in doc.locations:
        total_stock_qty += flt(row.get("picked_qty"), 4) or flt(row.get("stock_qty"), 4) or (
            flt(row.get("qty"), 4) * (flt(row.get("conversion_factor")) or 1)
        )

    # Get picklist allowance from Selling Settings
    picklist_allowance = frappe.db.get_single_value("Selling Settings", "custom_picklist_allowance") or 0
    picklist_allowance = flt(picklist_allowance, 2)

    # Calculate allowed quantity: SO qty * (1 + allowance/100)
    # Example: 40% allowance means 140% of SO qty is allowed.
    # Sales Order Item stock_qty is also in Stock UOM, so the ordered UOM never
    # skews the allowance check.
    sales_order_stock_qty = sum(
        flt(item.get("stock_qty"), 4) or flt(item.get("qty"), 4)
        for item in sales_order.items
    )
    sales_order_stock_qty = flt(sales_order_stock_qty, 4)
    allowed_qty = flt(sales_order_stock_qty * (1 + picklist_allowance / 100), 4)

    if flt(total_stock_qty, 4) > allowed_qty:
        if picklist_allowance > 0:
            frappe.throw(
                _("Total Picked quantity <b>{0}</b> cannot exceed allowed quantity <b>{1}</b> (Sales Order quantity <b>{2}</b> + {3}% allowance)").format(
                    total_stock_qty, allowed_qty, sales_order_stock_qty, picklist_allowance
                )
            )
        else:
            frappe.throw(
                _("Total Picked quantity <b>{0}</b> cannot exceed Sales Order quantity <b>{1}</b>").format(
                    total_stock_qty, sales_order_stock_qty
                )
            )
        
def before_save(doc, method=None):
    ensure_item_locations(doc)
    apply_sales_order_uom(doc)
    validate_item_batch(doc)
    validate_qty(doc)
    validate_custom_item_barcodes(doc)
    calculate_package_weight(doc)


def _resolve_row_sales_order_item(doc, row):
    """Sales Order Item (child table) row for a Pick List / child row."""
    return resolve_sales_order_item(
        item_code=row.get("item_code"),
        sales_order=row.get("sales_order") or doc.get("custom_sales_order"),
        sales_order_item=row.get("sales_order_item"),
    )


def ensure_item_locations(doc):
    """
    Safety net for the client-side rebuild: when the scanned Items table is used
    but the standard Item Locations table ended up empty, build it from the
    scanned rows (grouped by item + batch + warehouse).

    This keeps the Pick List usable even if the browser still runs an old script
    or the form was saved through the API.
    """
    if doc.get("locations"):
        return

    rows = [row for row in (doc.get("custom_items") or []) if row.get("item_code")]
    if not rows:
        return

    grouped = {}
    for row in rows:
        cf = flt(row.get("conversion_factor")) or 1
        key = (row.item_code, row.get("batch_no") or "", row.get("warehouse") or "")
        group = grouped.get(key)
        if not group:
            group = grouped[key] = frappe._dict(
                item_code=row.item_code,
                batch_no=row.get("batch_no") or "",
                warehouse=row.get("warehouse"),
                uom=row.get("uom"),
                stock_uom=row.get("stock_uom"),
                conversion_factor=cf,
                sales_order=row.get("sales_order"),
                sales_order_item=row.get("sales_order_item"),
                stock_qty=0.0,
                barcode_count=0,
            )
        group.stock_qty += flt(row.get("stock_qty")) or (flt(row.get("qty")) * cf)
        group.barcode_count += 1

    for group in grouped.values():
        cf = group.conversion_factor or 1
        doc.append(
            "locations",
            {
                "item_code": group.item_code,
                "warehouse": group.warehouse,
                "use_serial_batch_fields": 1,
                "batch_no": group.batch_no,
                "uom": group.uom or group.stock_uom,
                "stock_uom": group.stock_uom,
                "conversion_factor": cf,
                "qty": flt(group.stock_qty / cf, 4) if cf else group.stock_qty,
                "stock_qty": group.stock_qty,
                "picked_qty": group.stock_qty,
                "custom_barcode_no": group.barcode_count,
                "sales_order": group.sales_order,
                "sales_order_item": group.sales_order_item,
            },
        )


def sync_custom_items_uom(doc):
    """
    Keep the scanned rows (`custom_items`) consistent:

    - `qty` is always expressed in `uom` (the UOM the user chose; it defaults to
      the Sales Order child table UOM).
    - `stock_qty` is always the same quantity expressed in the Stock UOM.
    """
    for row in doc.get("custom_items") or []:
        if not row.get("barcode"):
            continue

        pack = get_tracker_qty_snapshot(row.barcode)
        if not pack:
            continue

        so_item = _resolve_row_sales_order_item(doc, row)
        chosen_uom = (
            row.get("uom")
            or (so_item.get("uom") if so_item else None)
            or pack.transaction_uom
            or pack.stock_uom
        )
        resolved = resolve_pack_qty_for_uom(
            chosen_uom,
            pack.stock_qty,
            pack.stock_uom,
            transaction_uom=pack.transaction_uom,
            transaction_qty=pack.transaction_qty,
            conversion_factor=pack.conversion_factor,
            uom_conversions=get_item_uom_conversions(pack.item_code),
        )

        row.uom = resolved["uom"]
        row.conversion_factor = resolved["conversion_factor"]
        row.qty = resolved["qty"]
        row.stock_uom = resolved["stock_uom"]
        row.stock_qty = resolved["stock_qty"]

        if so_item:
            row.sales_order = so_item.get("parent")
            row.sales_order_item = so_item.get("name")


def sync_locations_uom(doc):
    """
    Pick List Item (`locations`) rows are what the Delivery Note is mapped from,
    so they must carry the Sales Order Item (child table) UOM:

    - `uom` / `conversion_factor` come from the Sales Order Item (the ordered UOM)
    - `qty` is the same quantity expressed in that UOM
    - `stock_qty` / `picked_qty` stay in the Stock UOM
    """
    for row in doc.get("locations") or []:
        so_item = _resolve_row_sales_order_item(doc, row)
        if not so_item:
            continue

        stock_uom = so_item.get("stock_uom") or frappe.db.get_value(
            "Item", row.item_code, "stock_uom"
        )
        cf = flt(so_item.get("conversion_factor")) or get_uom_conversion_factor(
            row.item_code, so_item.get("uom"), stock_uom
        )
        cf = cf or 1.0

        # Stock UOM is the source of truth (it was validated against the pack).
        stock_qty = flt(row.get("picked_qty")) or flt(row.get("stock_qty"))
        if not stock_qty:
            stock_qty = flt(row.get("qty")) * (flt(row.get("conversion_factor")) or 1.0)

        row.sales_order = so_item.get("parent")
        row.sales_order_item = so_item.get("name")
        row.uom = so_item.get("uom") or stock_uom
        row.stock_uom = stock_uom
        row.conversion_factor = cf
        row.qty = flt(stock_qty / cf, row.precision("qty")) if cf else stock_qty
        # Never invent a picked qty: ERPNext keeps not-picked rows at 0 and fills
        # them from stock_qty on submit (or validates them in scan mode).
        if flt(row.get("picked_qty")):
            row.picked_qty = stock_qty
        if flt(row.get("stock_qty")):
            row.stock_qty = stock_qty


def apply_sales_order_uom(doc):
    """Entry point: align both Pick List tables with the ordered UOM."""
    sync_custom_items_uom(doc)
    sync_locations_uom(doc)


def validate_item_batch(doc):
    """A batch on a row must belong to the item chosen on that same row."""
    for row in doc.get("custom_items") or []:
        if not (row.get("item_code") and row.get("batch_no")):
            continue

        batch_item = frappe.db.get_value("Batch", row.batch_no, "item")
        if batch_item and batch_item != row.item_code:
            frappe.throw(
                _("Row {0}: Batch <b>{1}</b> belongs to <b>{2}</b>, not <b>{3}</b>.").format(
                    row.idx, row.batch_no, batch_item, row.item_code
                )
            )


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
    """
    Copy the packaging details entered on the scanned rows (custom Items table)
    onto the standard Item Locations rows and compute the gross weight.

    The scanned row is the source of truth; the Pick List level packaging fields
    are only a fallback (older pick lists that had no packaging on the rows).
    """
    packaging_by_item = {}
    for row in doc.get("custom_items") or []:
        if not row.get("item_code"):
            continue
        packaging_by_item.setdefault(row.item_code, row)

    for item in doc.locations:
        custom_row = packaging_by_item.get(item.item_code) or frappe._dict()
        barcode_count = flt(item.get("custom_barcode_no"))

        packaging_item = custom_row.get("packaging_item") or doc.get("custom_packaging_item")
        packing_weight = flt(custom_row.get("package_weight")) or flt(doc.get("custom_packing_weight"))
        packaging_itemuom = custom_row.get("packaging_itemuom") or doc.get("custom_packaging_itemuom")
        cubic = flt(custom_row.get("cubic")) or flt(doc.get("custom_cubic"))

        item.custom_packaging_item = packaging_item
        item.custom_packing_weight = packing_weight
        item.custom_packaging_itemuom = packaging_itemuom
        item.custom_cubic = cubic * barcode_count

        # Weight is physical, so always use the Stock UOM qty even when `qty` is
        # expressed in the ordered (transaction) UOM.
        qty_for_weight = flt(item.get("picked_qty")) or flt(item.qty)
        item.custom_gross_weight = (packing_weight * barcode_count) + qty_for_weight


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

        # Invoice in the Sales Order Item (child table) UOM; the stock qty on the
        # pick list row is the source of truth so partial packs stay correct.
        conversion_factor = flt(so_item.conversion_factor) or 1
        stock_qty = (
            flt(loc.get("picked_qty"))
            or flt(loc.get("stock_qty"))
            or (flt(loc.qty) * (flt(loc.get("conversion_factor")) or 1))
        )
        invoice_qty = stock_qty / conversion_factor if conversion_factor else flt(loc.qty)

        invoice.append("items", {
            "item_code": loc.item_code,
            "qty": invoice_qty,
            "uom": so_item.uom,
            "stock_uom": so_item.stock_uom,
            "conversion_factor": conversion_factor,
            "warehouse": loc.warehouse,
            "rate": so_item.rate,
            "base_rate": so_item.base_rate,
            "batch_no": loc.batch_no,
            # Keep the Pick List linkage so the invoice can flag / reopen the
            # pack barcodes when it moves stock or is cancelled.
            "pick_list_item": loc.name,
            "against_pick_list": picklist.name,
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


@frappe.whitelist()
def get_sales_order_items_for_pick_list(sales_order):
    """
    Items of the Sales Order linked to a Pick List, for the
    "Fetch Items From Order" dialog: ordered qty / UOM, warehouse, whether the
    item is batched, and how many unsold pack barcodes are available for it.
    """
    if not sales_order:
        frappe.throw(_("Link a Sales Order on this Pick List first."))

    if not frappe.db.exists("Sales Order", sales_order):
        frappe.throw(_("Sales Order {0} was not found.").format(sales_order))

    sales_order_doc = frappe.get_doc("Sales Order", sales_order)
    barcode_counts = _get_available_barcode_counts(
        [item.item_code for item in sales_order_doc.items]
    )

    rows = []
    for item in sales_order_doc.items:
        rows.append(
            {
                "sales_order_item": item.name,
                "item_code": item.item_code,
                "item_name": item.item_name,
                "description": item.description,
                "qty": flt(item.qty),
                "uom": item.uom,
                "stock_qty": flt(item.stock_qty),
                "stock_uom": item.stock_uom,
                "conversion_factor": flt(item.conversion_factor) or 1,
                # Pick List Item warehouse (Sales Order Item has no warehouse)
                "warehouse": sales_order_doc.get("set_warehouse"),
                "delivered_qty": flt(item.get("delivered_qty")),
                "has_batch_no": cint(
                    frappe.db.get_value("Item", item.item_code, "has_batch_no")
                ),
                "available_barcodes": barcode_counts.get(item.item_code, 0),
            }
        )

    return rows


def _get_available_barcode_counts(item_codes):
    """
    {item_code: number of Batch Barcode Trackers that can still be picked} -
    submitted, not sold and not already used in a submitted Pick List (same rule
    as `get_barcode_query`).
    """
    item_codes = sorted({code for code in item_codes if code})
    if not item_codes:
        return {}

    placeholders = ", ".join(["%s"] * len(item_codes))
    rows = frappe.db.sql(
        f"""
        SELECT bbt.item_code, COUNT(*) AS barcodes
        FROM `tabBatch Barcode Tracker` bbt
        WHERE bbt.docstatus = 1
            AND IFNULL(bbt.sold, 0) = 0
            AND bbt.item_code IN ({placeholders})
            AND bbt.name NOT IN (
                SELECT ple.barcode
                FROM `tabPick List Extension` ple
                INNER JOIN `tabPick List` pl ON ple.parent = pl.name
                WHERE pl.docstatus = 1
                    AND ple.barcode IS NOT NULL
                    AND ple.barcode != ''
            )
        GROUP BY bbt.item_code
        """,
        tuple(item_codes),
        as_dict=True,
    )

    return {row.item_code: cint(row.barcodes) for row in rows}

