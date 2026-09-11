frappe.ui.form.on('Subcontracting Receipt', {
    custom_split_items: function(frm) {
        split_items_(frm);
    },

    refresh: function(frm) {
        frm.add_custom_button(__('Split Items'), function() {
            split_items_(frm);
        });
        setup_supplied_batch_barcode_filters(frm);
    },

    supplier_warehouse: function(frm) {
        setup_supplied_batch_barcode_filters(frm);
    },

    before_save: function(frm) {
        validate_no_duplicate_batch_barcodes(
            frm.doc.supplied_items || [],
            'custom_batch_barcode'
        );
    }
});

frappe.ui.form.on('Subcontracting Receipt Item', {
    qty: function(frm, cdt, cdn) {
        barcode_image(frm, cdt, cdn);
    },
    custom_print: function(frm, cdt, cdn) {
        print_barcode(frm, cdt, cdn);
    }
});

frappe.ui.form.on('Subcontracting Receipt Supplied Item', {
    batch_no: function(frm, cdt, cdn) {
        setup_supplied_batch_barcode_filters(frm);
    },
    custom_batch_barcode: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (!row.custom_batch_barcode) {
            setup_supplied_batch_barcode_filters(frm);
            return;
        }

        let duplicate = (frm.doc.supplied_items || []).some(
            r => r.name !== cdn && r.custom_batch_barcode === row.custom_batch_barcode
        );
        if (duplicate) {
            frappe.msgprint(__('Batch Barcode {0} is already selected on another raw material row.', [row.custom_batch_barcode]));
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
                if (pack.item_code && row.rm_item_code && pack.item_code !== row.rm_item_code) {
                    frappe.msgprint(__(
                        'Batch Barcode {0} belongs to {1}, not {2}.',
                        [pack.barcode, pack.item_code, row.rm_item_code]
                    ));
                    frappe.model.set_value(cdt, cdn, 'custom_batch_barcode', '');
                    return;
                }

                if (row.consumed_qty && pack.stock_qty
                    && Math.abs(flt(row.consumed_qty) - flt(pack.stock_qty)) > 0.00001) {
                    frappe.msgprint({
                        title: __('Qty / UOM mismatch'),
                        indicator: 'orange',
                        message: __(
                            'Consumed qty is {0} {1}, but pack {2} has {3} {4} (transaction: {5} {6}). Packs must be consumed in full.',
                            [
                                row.consumed_qty,
                                row.stock_uom || pack.stock_uom || '',
                                pack.barcode,
                                pack.stock_qty,
                                pack.stock_uom || '',
                                pack.transaction_qty,
                                pack.transaction_uom || ''
                            ]
                        )
                    });
                }

                if (pack.batch) {
                    frappe.model.set_value(cdt, cdn, 'use_serial_batch_fields', 1);
                    frappe.model.set_value(cdt, cdn, 'batch_no', pack.batch);
                }
                setup_supplied_batch_barcode_filters(frm);
            }
        });
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

function setup_supplied_batch_barcode_filters(frm) {
    if (!frm.fields_dict.supplied_items) {
        return;
    }

    frm.set_query('custom_batch_barcode', 'supplied_items', function(doc, cdt, cdn) {
        let row = locals[cdt][cdn];
        let filters = {
            sold: 0
        };

        if (row.rm_item_code) {
            filters.item_code = row.rm_item_code;
        }
        if (row.batch_no) {
            filters.batch = row.batch_no;
        }
        if (doc.supplier_warehouse) {
            filters.warehouse = doc.supplier_warehouse;
        }

        // Hide barcodes already picked on other consumed RM rows
        let selected = get_selected_batch_barcodes(
            doc.supplied_items,
            cdn,
            'custom_batch_barcode'
        );
        if (selected.length) {
            filters.name = ['not in', selected];
        }

        return { filters: filters };
    });
}

function split_items_(frm) {
    let has_split = frm.doc.items.some(item => item.custom_split_no > 1);
    if (has_split) {
        frappe.call({
            method: "inventory_management_extension.inventory_management_extension.utils.split_subcontracting_receipt_items",
            args: {
                subcontracting_receipt: frm.doc.name,
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

function barcode_image(frm, cdt, cdn) {
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

function print_barcode(frm, cdt, cdn) {
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
                    width: 8cm;
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
            <p><strong>Batch:</strong> ${item.batch_no || ''}</p>
            <p><strong>Qty:</strong> ${item.qty || ''}</p>
            <p><strong>Manufactured Date:</strong> ${frm.doc.posting_date || ''}</p>
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
