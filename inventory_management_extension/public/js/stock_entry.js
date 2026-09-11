frappe.ui.form.on('Stock Entry', {
    custom_split_items: function(frm) {
        split_iems_(frm);
    },

    refresh: function(frm) {
        frm.add_custom_button(__('Split Items'), function() {
            split_iems_(frm);
        });
        setup_batch_barcode_filters(frm);
    },

    items_add: function(frm) {
        setup_batch_barcode_filters(frm);
    },

    before_save: function(frm) {
        validate_no_duplicate_batch_barcodes(frm.doc.items || [], 'custom_batch_barcode');
    }
});

frappe.ui.form.on('Stock Entry Detail', {
    qty: function(frm, cdt, cdn) {
        barcode_image(frm, cdt, cdn);
    },
    custom_print: function(frm, cdt, cdn){
        print(frm, cdt, cdn);
    },
    batch_no: function(frm, cdt, cdn) {
        setup_batch_barcode_filters(frm);
    },
    s_warehouse: function(frm, cdt, cdn) {
        setup_batch_barcode_filters(frm);
    },
    item_code: function(frm, cdt, cdn) {
        setup_batch_barcode_filters(frm);
    },
    custom_batch_barcode: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.custom_batch_barcode) {
            let duplicate = (frm.doc.items || []).some(
                r => r.name !== cdn && r.custom_batch_barcode === row.custom_batch_barcode
            );
            if (duplicate) {
                frappe.msgprint(__('Batch Barcode {0} is already selected on another row.', [row.custom_batch_barcode]));
                frappe.model.set_value(cdt, cdn, 'custom_batch_barcode', '');
                return;
            }

            frappe.call({
                method: 'inventory_management_extension.inventory_management_extension.utils.get_batch_barcode_pack_details',
                args: {
                    barcode: row.custom_batch_barcode
                },
                callback: function(r) {
                    if (!r.message) {
                        return;
                    }
                    let pack = r.message;
                    if (pack.sold) {
                        frappe.msgprint(__('This barcode is already sold/consumed.'));
                        frappe.model.set_value(cdt, cdn, 'custom_batch_barcode', '');
                        return;
                    }
                    if (row.item_code && pack.item_code && row.item_code !== pack.item_code) {
                        frappe.msgprint(__(
                            'Batch Barcode {0} belongs to {1}, not {2}.',
                            [pack.barcode, pack.item_code, row.item_code]
                        ));
                        frappe.model.set_value(cdt, cdn, 'custom_batch_barcode', '');
                        return;
                    }
                    if (!row.item_code && pack.item_code) {
                        frappe.model.set_value(cdt, cdn, 'item_code', pack.item_code);
                    }

                    // Keep whatever UOM the user already chose (stock or transaction).
                    // Only fill qty for that UOM; conversion is validated on save.
                    let chosen_uom = row.uom || pack.transaction_uom || pack.stock_uom;
                    let qty_for_uom = null;
                    let conversion = pack.conversion_factor || 1;

                    if (chosen_uom && pack.transaction_uom && chosen_uom === pack.transaction_uom) {
                        qty_for_uom = pack.transaction_qty;
                        conversion = pack.conversion_factor || 1;
                    } else if (chosen_uom && pack.stock_uom && chosen_uom === pack.stock_uom) {
                        qty_for_uom = pack.stock_qty;
                        conversion = 1;
                    } else if (!row.uom) {
                        chosen_uom = pack.stock_uom || pack.uom;
                        qty_for_uom = pack.stock_qty || pack.qty;
                        conversion = 1;
                        if (chosen_uom) {
                            frappe.model.set_value(cdt, cdn, 'uom', chosen_uom);
                        }
                    } else {
                        qty_for_uom = pack.stock_qty || pack.qty;
                    }

                    if (conversion) {
                        frappe.model.set_value(cdt, cdn, 'conversion_factor', conversion);
                    }
                    if (qty_for_uom) {
                        frappe.model.set_value(cdt, cdn, 'qty', qty_for_uom);
                    }
                    if (pack.batch) {
                        frappe.model.set_value(cdt, cdn, 'batch_no', pack.batch);
                        frappe.model.set_value(cdt, cdn, 'use_serial_batch_fields', 1);
                    }
                    setup_batch_barcode_filters(frm);
                }
            });
        } else {
            setup_batch_barcode_filters(frm);
        }
    }
});

function get_selected_batch_barcodes(rows, current_cdn, fieldname) {
    return (rows || [])
        .filter(r => r.name !== current_cdn && r[fieldname])
        .map(r => r[fieldname]);
}

function validate_no_duplicate_batch_barcodes(rows, fieldname) {
    let seen = {};
    let duplicates = [];
    (rows || []).forEach(row => {
        let barcode = row[fieldname];
        if (!barcode) return;
        if (seen[barcode]) {
            if (!duplicates.includes(barcode)) {
                duplicates.push(barcode);
            }
        } else {
            seen[barcode] = true;
        }
    });
    if (duplicates.length) {
        frappe.throw(__(
            'Batch Barcode(s) selected more than once: {0}',
            [duplicates.join(', ')]
        ));
    }
}

function setup_batch_barcode_filters(frm) {
    if (!frm.fields_dict.items) return;

    frm.set_query('custom_batch_barcode', 'items', function(doc, cdt, cdn) {
        let row = locals[cdt][cdn];
        let filters = {
            sold: 0
        };

        if (row.batch_no) {
            filters.batch = row.batch_no;
        }
        if (row.item_code) {
            filters.item_code = row.item_code;
        }
        if (row.s_warehouse) {
            filters.warehouse = row.s_warehouse;
        }

        // Hide barcodes already picked on other rows (same as Pick List)
        let selected = get_selected_batch_barcodes(doc.items, cdn, 'custom_batch_barcode');
        if (selected.length) {
            filters.name = ['not in', selected];
        }

        return { filters: filters };
    });
}

function split_iems_(frm){
    let has_split = frm.doc.items.some(item => item.custom_split_no > 1);
    if (has_split) {
        frappe.call({
            method: "inventory_management_extension.inventory_management_extension.utils.split_stock_entry_items",
            args: {
                stock_entry: frm.doc.name,
            },
            callback: function(r) {
                if (r.message) {
                    frm.refresh();
                    frappe.show_alert({
                        message: __('Items successfully split'),
                        indicator: 'green'
                    });
                }
            },
            freeze: true,
            freeze_message: __('Splitting items...')
        });
    } else {
        frappe.msgprint(__('Please set split count greater than 1 for this item.'));
    }
}

function barcode_image(frm, cdt, cdn){
    let item = locals[cdt][cdn];
    if (item.custom_transaction_barcode) {
        frappe.call({
            method: "inventory_management_extension.inventory_management_extension.utils.generate_image_for_barcode",
            args: {
                barcode: item.custom_transaction_barcode,
            },
            callback: function(r) {
                if (r.message) {
                    item.custom_barcode_image = r.message;
                    frm.refresh_field('items');
                }
            }
        });
    }
}

function print(frm, cdt, cdn){
        let item = locals[cdt][cdn];

        if (!item.custom_barcode_image) {
            frappe.msgprint(__('No barcode image found for this item.'));
            return;
        }

        let printWindow = window.open('', '_blank');
        printWindow.document.open();
        printWindow.document.write(`
            <html>
            <head>
                <style>
                    body {
                        text-align: center;
                        font-family: Arial, sans-serif;
                        width:8cm;
                        height: 10cm;
                    }
                    img {
                        max-width: 100%;
                        height: auto;
                    }
                </style>
            </head>
            <body>
                  <p><strong>Item Code:</strong> ${item.item_code || ''}</p>
                <p><strong>Batch:</strong> ${item.batch_no}</p>
                <p><strong>Qty(Nos):</strong> ${item.qty}</p>
                <p><strong>Manufactured Date:</strong> ${frm.doc.posting_date}</p>
                <img src="${item.custom_barcode_image}" alt="Barcode Image" />
                <script>
                    window.onload = function() {
                        window.print();
                        window.onafterprint = function() {
                            window.close();
                        };
                    };
                </script>
            </body>
            </html>
        `);
        printWindow.document.close();
    }
