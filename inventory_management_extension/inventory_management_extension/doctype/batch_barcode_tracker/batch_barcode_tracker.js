// Copyright (c) 2025, nei and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Batch Barcode Tracker", {
// 	refresh(frm) {
// alert("Mania")
// 	},
// });

// frappe.listview_settings['Batch Barcode Tracker'] = {
//     onload: function(listview) {
//         frappe.throw('This is a custom list view for Batch Barcode Tracker. Please use the standard interface for other documents.');
//         // Create a custom input field
//         let input = $(`<input type="text" placeholder="Scan Barcode" class="form-control" style="width: 200px; margin-left: 10px;">`);

//         // Add the field next to the filters
//         listview.page.add_inner_button(' ', () => {}, 'Scan Barcode').parent().html(input);

//         // Handle barcode input (press Enter or scan)
//         input.on('keypress', function(e) {
//             if (e.which === 13) {
//                 const barcode = input.val().trim();
//                 if (barcode) {
//                     listview.filter_area.add([[ "Barcode Tracker", "barcode", "=", barcode ]]);
//                     input.val(''); // Clear input
//                 }
//             }
//         });
//     }
// };
// frappe.listview_settings['Batch Barcode Tracker'] = {
//     onload: function(listview) {
//         frappe.msgprint(__('This is a custom list view for Batch Barcode Tracker. Please use the standard interface for other documents.'));
//     }
// };

