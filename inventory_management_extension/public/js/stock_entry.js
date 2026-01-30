frappe.ui.form.on('Stock Entry', {
    
    custom_split_items: function(frm) {
      split_iems_(frm);
    },

    refresh: function(frm) {
        frm.add_custom_button(__('Split Items'), function() {
            split_iems_(frm);
        });
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
        setup_batch_barcode_filter(frm, cdt, cdn);
    },
    custom_batch_barcode: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.custom_batch_barcode) {
            // Auto-fill item details and quantity from batch barcode tracker
            frappe.call({
                method: 'frappe.client.get',
                args: {
                    doctype: 'Batch Barcode Tracker',
                    name: row.custom_batch_barcode
                },
                callback: function(r) {
                    if (r.message) {
                        // Auto-fill item code if not already set
                        if (!row.item_code) {
                            frappe.model.set_value(cdt, cdn, 'item_code', r.message.item_code);
                        }
                        // Auto-fill quantity from batch barcode tracker
                        if (r.message.qty) {
                            frappe.model.set_value(cdt, cdn, 'qty', r.message.qty);
                        }
                    }
                }
            });
        }
    }
});

frappe.ui.form.on('Stock Entry', {
    refresh: function(frm) {
        setup_batch_barcode_filters(frm);
    },
    items_add: function(frm) {
        setup_batch_barcode_filters(frm);
    }
});

function setup_batch_barcode_filters(frm) {
    if (!frm.fields_dict.items) return;
    
    frm.fields_dict.items.grid.get_field("custom_batch_barcode").get_query = function(doc, cdt, cdn) {
        let row = locals[cdt][cdn];
        let filters = {
            "sold": 0
        };
        
        if (row.batch_no) {
            filters["batch"] = row.batch_no;
        }
        
        if (row.item_code) {
            filters["item_code"] = row.item_code;
        }
        
        // Filter by source warehouse so only barcodes in that warehouse are shown
        if (row.s_warehouse) {
            filters["warehouse"] = row.s_warehouse;
        }
        
        return {
            filters: filters
        };
    };
}

function setup_batch_barcode_filter(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    if (row.batch_no) {
        frm.fields_dict.items.grid.get_field("custom_batch_barcode").get_query = function(doc, cdt, cdn) {
            let current_row = locals[cdt][cdn];
            let filters = {
                "batch": current_row.batch_no || row.batch_no,
                "item_code": current_row.item_code || row.item_code,
                "sold": 0
            };
            if (current_row.s_warehouse) {
                filters["warehouse"] = current_row.s_warehouse;
            }
            return { filters: filters };
        };
        frm.refresh_field('items');
    }
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
                // width: 200,
                // height: 100
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

        // Open a new print window
        let printWindow = window.open('', '_blank');
        printWindow.document.open();
        printWindow.document.write(`
            <html>
            <head>
                <style>
                    body {
                        text-align: center;
                        font-family: Arial, sans-serif;
                        width:8cm,
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
