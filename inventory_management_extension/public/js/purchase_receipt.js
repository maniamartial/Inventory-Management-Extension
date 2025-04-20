frappe.ui.form.on('Purchase Receipt', {
    
    custom_split_items: function(frm) {
      split_iems_(frm);
    },

    refresh: function(frm) {
        frm.add_custom_button(__('Split Items'), function() {
            split_iems_(frm);
        });
    }
});

frappe.ui.form.on('Purchase Receipt Item', {
    qty: function(frm, cdt, cdn) {
        barcode_image(frm, cdt, cdn);
    },
    custom_print: function(frm, cdt, cdn){
        print(frm, cdt, cdn);
    }
    
})

function split_iems_(frm){
    let has_split = frm.doc.items.some(item => item.custom_split_no > 1);
    if (has_split) {
        frappe.call({
            method: "inventory_management_extension.inventory_management_extension.utils.split_purchase_receipt_items",
            args: {
                purchase_receipt: frm.doc.name,
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
                <title>Print Barcode</title>
                <style>
                    body {
                        text-align: center;
                        font-family: Arial, sans-serif;
                    }
                    img {
                        max-width: 100%;
                        height: auto;
                    }
                </style>
            </head>
            <body>
                <h3>Barcode for Item: ${item.item_name || ''}</h3>
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
