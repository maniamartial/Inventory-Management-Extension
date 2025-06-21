
# 📦 Inventory Management Extension

**Inventory Management Extension** is an ERPNext add-on that improves inventory traceability using barcodes. It streamlines barcode handling during purchasing, manufacturing, and sales, enabling users to track individual packages or splits from batches all the way through delivery.

----------

## 🧩 Key Features

-   Barcode generation for incoming and manufactured stock.
    
-   Support for quantity **splits**, generating multiple barcodes from a single batch.
    
-   Barcode tracking across all stages: Purchase, Manufacturing, Sales.
    
-   Easy barcode printing per line item.
    
-   Enhanced Pick List process with barcode selection and scanning.
    
-   Batch-based delivery verification.
    

----------

## 🔍 Workflow Overview

### 1. **Purchase Transactions (Purchase Receipt / Purchase Invoice)**

-   A new field called `transactional_barcode_tracker` is added to the child item table.
    
-   Barcodes are automatically generated before saving using the **EAN format**.
    
-   **Split Functionality**:
    
    -   Enter a value in the `split` custom field (e.g., 20).
        
    -   This **creates 20 line items** and **splits the quantity evenly** across them.
        
-   A **Print button is available per line item**:
    
    -   When you change the quantity, a transaction barcode is generated (if unsaved).
        
    -   You can **print the barcode** and physically attach it to the package.
        ![image (40)](https://github.com/user-attachments/assets/b8b2c34c-712c-45f3-aeaf-8d07f2d04ed5)


#### 📄 On Submission:

-   Barcode records are saved into a new doctype: **Batch Barcode Tracker**, which contains:
    
    -   Batch Number
        
    -   Barcode Image
        
    -   Quantity
        
    -   Warehouse
        
    -   Item Code
     ![image (39)](https://github.com/user-attachments/assets/9ee36770-f4ca-4d12-900f-6e0372d59ee8)
   

----------

### 2. **Manufacturing (Stock Entry: Repack / Manufacture / Material Receipt)**

-   For **Repack** and **Manufacture**:
    
    -   Source items are listed as usual.
        
    -   Target warehouse items (finished goods) trigger barcode creation.
        
-   For **Material Receipts**:
    
    -   Any item line with a batch will also trigger **transaction barcode creation**.
        

On **submission**, each target item line results in a record in **Batch Barcode Tracker**.
![image (40)](https://github.com/user-attachments/assets/3c34184b-a415-471e-b5ed-8582ead00052)


----------

### 3. **Sales Workflow**

####  Sales Order → Pick List → Delivery Note → Sales Invoice

- Customer orders specific batch items. Use creates sales order. 

-   Pick List is **not automatically generated**.
    
-   User creates Pick List  **manually from Sales Order**.
    

####  Pick List Extension

-   A custom child table `Pick List Extension` is introduced.
    
    -   It mirrors `Pick List Items` but includes an extra `barcode` field.
        
-   The user selects a warehouse (manual or automatic).
    
-   The **barcode field is filtered** to show:
    
    -   Barcodes from **Batch Barcode Tracker**
        
    -   Belonging to the selected batch
        
    -   Not already used in another line
      ![image (38)](https://github.com/user-attachments/assets/28e781a7-7315-4320-b54b-6c54d8ee90c9)

        

#### Barcode Handling:

-   Scanning supported via the **`scan_transactional_barcodes`** field.
    
    -   When a barcode is scanned:
        
        -   A new line is added with the related item, warehouse, and batch.
            
-   When saved:
    
    -   Pick List groups by batch and totals quantities accordingly.
        
    -   Barcodes can be printed for dispatch or logistics visibility.
        
![Screenshot 2025-06-21 at 13 05 14](https://github.com/user-attachments/assets/909501f6-102a-42d9-b153-bdda46508832)

----------

### 4. **Delivery Note and Sales Invoice**

-   Upon submitting the **Delivery Note**:
    
    -   Barcodes in **Batch Barcode Tracker** are marked as `Sold = Yes`.
        
    -   ERPNext also handles batch consumption as per standard rules.
        
-   Sales Invoice is created and submitted using the standard ERPNext process.
    

----------


## 📄 Summary of New/Extended Doctypes and Fields

| Doctype                  | Field / Extension                | Description                                                                 |
|--------------------------|----------------------------------|-----------------------------------------------------------------------------|
| Purchase Receipt / Invoice | `transactional_barcode_tracker` | Tracks barcodes per line item                                               |
| Purchase Receipt / Invoice | `split`                         | Splits quantity into multiple line items and generates barcodes             |
| Purchase Receipt / Invoice | Line Item Print Button          | Allows barcode printing per line item                                       |
| Batch Barcode Tracker (New) | `batch`, `barcode_image`, `qty`, `warehouse`, `item`, `sold` | Tracks each barcode against its batch, item, and warehouse                 |
| Stock Entry              | Repack / Manufacture Logic       | Generates barcodes for finished goods in target warehouse                   |
| Pick List                | `Pick List Extension` (child table) | Mirrors item lines but includes barcodes                                   |
| Pick List                | `scan_transactional_barcodes`    | Field to scan barcodes directly into the pick list                          |
| Delivery Note            | –                                | Submits and marks barcodes as sold                                          |
| Sales Invoice            | –                                | Follows ERPNext standard flow                                               |


----------

## Barcode Printing

Barcodes printed include:

-   Item Code and Name
    
-   Quantity
    
-   Barcode Image
    
-   Batch Number.
    

Print options are available:

-   Per line item in Purchase Receipt / Invoice
    
-   In Pick List (for dispatch purposes)
- Batch Barcodes TRansaction
    

----------

## 🚚 Logistics Support

-   Barcodes provide clear identifiers for packaged items.
    
-   Assists warehouse and delivery teams in picking, verifying, and transporting items efficiently.
    
-   Helps prevent errors in dispatch and improves inventory visibility.
    

----------

## ✅ Benefits

-   Simplifies inventory tracking using barcodes.
    
-   Enhances traceability from manufacturing to customer delivery.
    
-   Reduces manual errors in stock handling.
    
-   Supports unit-level packaging and logistics workflows.
    
-   Integrates tightly with ERPNext’s standard batch and stock systems.
