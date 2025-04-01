frappe.ui.form.on('Stock Entry', {
    
    custom_split_items: function(frm) {
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
});

// frappe.ui.form.on('Stock Entry Detail', {
//     custom_split_no: function(frm, cdt, cdn) {
//         let row = locals[cdt][cdn];
//         let has_split = row.custom_split_no > 1;
//         if (has_split) {
//             frappe.call({
//                 method: "inventory_management_extension.inventory_management_extension.utils.split_stock_entry_items",
//                 args: {
//                     stock_entry: frm.doc.name,
//                 },
//                 callback: function(r) {
//                     if (r.message) {
//                         frm.refresh();
//                         frappe.show_alert({
//                             message: __('Item successfully split'),
//                             indicator: 'green'
//                         });
//                     }
//                 },
//                 freeze: true,
//                 freeze_message: __('Splitting item...')
//             });
//         } else {
//             frappe.msgprint(__('Please set split count greater than 1 for this item.'));
//         }
//     }
// });