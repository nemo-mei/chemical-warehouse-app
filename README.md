# Chemical Warehouse Management System

## 1. Project Overview

The **Chemical Warehouse Management System** is a Streamlit multi-page web application backed by PostgreSQL.  
It is designed for warehouse administrators in a chemical enterprise to manage:

- chemical master data
- warehouses
- storage locations
- inbound and outbound stock documents
- inventory queries
- stocktake sessions

The system helps warehouse staff record stock movement accurately, track inventory by warehouse, location, and batch, support inventory counting and reconciliation, and quickly search current inventory and recent transactions.

---

## 2. Technology Stack

- **Frontend:** Streamlit
- **Database:** PostgreSQL
- **Database Access:** psycopg2
- **Deployment Target:** Streamlit Community Cloud

---

## 3. Main Features

### Home Dashboard
- shows total chemicals
- shows total warehouses
- shows total inventory quantity
- shows low-stock item count
- shows recent stock document records

### Manage Chemicals
- add chemical records
- view all chemicals
- edit chemicals
- delete chemicals with confirmation
- search by SKU, chemical name, and category

### Manage Warehouses and Locations
- add warehouse records
- add storage locations
- view and search warehouses and locations
- edit and delete records with confirmation

### Stock In/Out Management
- create inbound and outbound stock documents
- add one or more item lines
- view document headers and item lines
- edit and delete records
- validate outbound quantity against available stock

### Inventory Query
- calculate current inventory from stock transactions
- group inventory by chemical, warehouse, location, and batch
- filter by SKU, chemical name, warehouse, location, and low-stock-only
- display expiry information when available

### Stocktake Management
- create stocktake sessions
- add stocktake item lines
- compare system quantity and counted quantity
- calculate variance
- view stocktake history
- edit and delete sessions with confirmation

---

## 4. Project Structure

```text
chemical_warehouse_management_system/
│
├── streamlit_app.py
├── db.py
├── validation.py
├── queries.py
├── ui_helpers.py
├── requirements.txt
├── README.md
├── ai_prompts.md
│
├── pages/
│   ├── 1_Manage_Chemicals.py
│   ├── 2_Manage_Warehouses_and_Locations.py
│   ├── 3_Stock_In_Out_Management.py
│   ├── 4_Inventory_Query.py
│   └── 5_Stocktake_Management.py
│
└── .streamlit/
    └── secrets.toml