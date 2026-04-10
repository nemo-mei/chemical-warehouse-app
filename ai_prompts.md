You are acting as a senior systems analyst, database designer, and Streamlit/PostgreSQL developer.

I am building an individual course project: a Streamlit multi-page web application backed by PostgreSQL for a chemical enterprise warehouse management system. The main user is a warehouse administrator. The system is used for inventory counting, inbound stock management, outbound stock management, and inventory lookup.

You must follow these implementation conventions exactly:

Project structure conventions:
- Use `streamlit_app.py` as the root entry-point home page file.
- Use a `pages/` folder for all other pages.
- Prefix page filenames with numbers like `1_`, `2_`, `3_` so Streamlit sidebar navigation appears in a logical order.
- Use `requirements.txt`.
- The project must be deployment-ready for Streamlit Community Cloud.
- The database connection must use `psycopg2.connect(st.secrets["DB_URL"])`.
- Do not hard-code credentials anywhere in Python files.
- Assume local development may use `.streamlit/secrets.toml`, but do not place secrets in the repository.

Technical constraints:
- Use Streamlit for the frontend.
- Use PostgreSQL as the database.
- Use psycopg2 for database access.
- Use parameterized SQL queries only. Never build SQL using f-strings or string concatenation.
- The app must support CRUD operations.
- Delete actions must require explicit confirmation before deleting.
- All dropdown/select options must come from database tables, not hard-coded Python lists, unless the options are fixed business enums already enforced by the schema.
- The app must include at least one search/filter feature.
- The home page must include a dashboard with live database metrics.
- Validation errors should be collected into a list and shown all at once before any database write.
- Show user-friendly error messages, not raw tracebacks.
- Keep code clean, readable, commented, and beginner-friendly enough for a college systems project.

My project concept:

System name:
Chemical Warehouse Management System

System description:
This system is for warehouse administrators in a chemical company. It manages chemical master data, warehouse information, storage locations, inbound and outbound stock documents, stocktake sessions, and inventory queries. The goal is to help warehouse staff record stock movement accurately, track inventory by warehouse, location, and batch, support counting and reconciliation, and quickly search current inventory, low-stock items, and recent transactions.

Database entities and attributes:

1) categories
- id SERIAL PRIMARY KEY
- category_name VARCHAR(100) UNIQUE NOT NULL
- description TEXT

2) chemicals
- id SERIAL PRIMARY KEY
- sku VARCHAR(50) UNIQUE NOT NULL
- chemical_name VARCHAR(150) NOT NULL
- cas_no VARCHAR(50)
- specification VARCHAR(100)
- unit VARCHAR(20) NOT NULL
- hazard_level VARCHAR(50)
- category_id INTEGER REFERENCES categories(id)
- min_stock NUMERIC(12,2) DEFAULT 0 CHECK (min_stock >= 0)
- is_active BOOLEAN DEFAULT TRUE
- created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

3) warehouses
- id SERIAL PRIMARY KEY
- warehouse_name VARCHAR(100) UNIQUE NOT NULL
- warehouse_code VARCHAR(30) UNIQUE NOT NULL
- address VARCHAR(200)
- manager_name VARCHAR(100)
- is_active BOOLEAN DEFAULT TRUE

4) storage_locations
- id SERIAL PRIMARY KEY
- warehouse_id INTEGER NOT NULL REFERENCES warehouses(id) ON DELETE CASCADE
- location_code VARCHAR(50) NOT NULL
- location_type VARCHAR(50)
- capacity NUMERIC(12,2) CHECK (capacity >= 0)
- is_active BOOLEAN DEFAULT TRUE
- UNIQUE (warehouse_id, location_code)

5) stock_documents
- id SERIAL PRIMARY KEY
- doc_no VARCHAR(50) UNIQUE NOT NULL
- doc_type VARCHAR(20) NOT NULL CHECK (doc_type IN ('INBOUND', 'OUTBOUND'))
- warehouse_id INTEGER NOT NULL REFERENCES warehouses(id)
- transaction_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
- operator_name VARCHAR(100) NOT NULL
- counterparty_name VARCHAR(150)
- notes TEXT
- created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

6) stock_document_items
- id SERIAL PRIMARY KEY
- document_id INTEGER NOT NULL REFERENCES stock_documents(id) ON DELETE CASCADE
- chemical_id INTEGER NOT NULL REFERENCES chemicals(id)
- location_id INTEGER NOT NULL REFERENCES storage_locations(id)
- batch_no VARCHAR(50)
- manufacture_date DATE
- expiry_date DATE
- quantity NUMERIC(12,2) NOT NULL CHECK (quantity > 0)
- unit_price NUMERIC(12,2) DEFAULT 0 CHECK (unit_price >= 0)

7) stocktake_sessions
- id SERIAL PRIMARY KEY
- session_name VARCHAR(100) NOT NULL
- warehouse_id INTEGER NOT NULL REFERENCES warehouses(id)
- planned_date DATE NOT NULL
- completed_date DATE
- status VARCHAR(20) NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'COMPLETED'))
- operator_name VARCHAR(100) NOT NULL
- notes TEXT

8) stocktake_items
- id SERIAL PRIMARY KEY
- session_id INTEGER NOT NULL REFERENCES stocktake_sessions(id) ON DELETE CASCADE
- chemical_id INTEGER NOT NULL REFERENCES chemicals(id)
- location_id INTEGER NOT NULL REFERENCES storage_locations(id)
- batch_no VARCHAR(50)
- system_quantity NUMERIC(12,2) NOT NULL CHECK (system_quantity >= 0)
- counted_quantity NUMERIC(12,2) NOT NULL CHECK (counted_quantity >= 0)

Relationships:
- One category has many chemicals.
- One warehouse has many storage locations.
- One warehouse has many stock documents.
- One stock document has many stock document items.
- One chemical can appear in many stock documents.
- Therefore, stock_documents and chemicals form a many-to-many relationship through stock_document_items.
- One stocktake session has many stocktake items.
- One chemical can appear in many stocktake sessions.

Page plan:
1. Home Dashboard (`streamlit_app.py`)
- Show total chemicals, total warehouses, total current inventory quantity, and low-stock item count.
- Show recent stock document records.
- Show monthly inbound and outbound summary.
- Include a brief welcome/instruction message telling the user to use the sidebar.

2. Manage Chemicals (`pages/1_Manage_Chemicals.py`)
- Add chemical form.
- View all chemicals.
- Edit chemical records.
- Delete chemical records with confirmation.
- Search/filter by SKU, chemical name, and category.

3. Manage Warehouses and Locations (`pages/2_Manage_Warehouses_and_Locations.py`)
- Add warehouse form.
- Add storage location form.
- View warehouse and location records.
- Edit/delete records with confirmation.
- Ensure location choices are tied to a selected warehouse where appropriate.

4. Stock In/Out Management (`pages/3_Stock_In_Out_Management.py`)
- Create stock document header.
- Add one or more stock item lines.
- Support both inbound and outbound documents.
- View all stock documents and related item lines.
- Edit/delete records with confirmation.
- Filter by document number, type, warehouse, and date range.

5. Inventory Query (`pages/4_Inventory_Query.py`)
- Show current inventory grouped by chemical, warehouse, location, and batch.
- Support search/filter by SKU, chemical name, warehouse, location, and low-stock-only.
- Calculate on-hand quantity from stock_documents + stock_document_items, where INBOUND adds quantity and OUTBOUND subtracts quantity.
- Show expiry-date-related information when available.

6. Stocktake Management (`pages/5_Stocktake_Management.py`)
- Create stocktake sessions.
- Add stocktake item lines.
- Show system quantity, counted quantity, and variance.
- View stocktake history.
- Edit/delete stocktake sessions with confirmation.

Validation rules:
- sku is required and must be unique.
- chemical_name is required.
- unit is required.
- min_stock must be numeric and >= 0.
- warehouse_name and warehouse_code are required and must be unique.
- location_code cannot repeat within the same warehouse.
- doc_no is required and must be unique.
- quantity must be > 0.
- unit_price must be >= 0.
- manufacture_date must be <= expiry_date when both are provided.
- outbound quantity cannot exceed available stock for the selected chemical/location/batch.
- counted_quantity must be >= 0.
- required fields cannot be blank.
- delete actions must require explicit confirmation.

Coding style expectations:
- Use `st.set_page_config()` in the home page.
- Use `st.title()`, `st.subheader()`, `st.metric()`, `st.columns()`, `st.dataframe()` or `st.table()` where appropriate.
- Use `st.form()` for data entry forms.
- Use sidebar navigation automatically via Streamlit pages.
- Use helper functions to reduce duplication.
- Close cursors and connections properly.
- Commit only when writes succeed.
- Roll back transactions on failure where needed.
- Handle duplicate key errors gracefully.
- Avoid advanced abstractions that would make the project hard to explain in class.

What I want from you:
Work in phases and do not skip steps.

Phase 1:
Produce:
A. A polished system description paragraph
B. Full entity list with attributes, data types, and constraints
C. Relationships list
D. Page-by-page feature plan
E. Validation rules
F. ERD in dbdiagram.io syntax

Phase 2:
Generate PostgreSQL DDL statements to create all tables in the correct order.

Phase 3:
Generate the exact project folder/file structure using:
- `streamlit_app.py`
- `pages/`
- shared helper modules such as `db.py`, `validation.py`, and optional utility files
- `requirements.txt`
- `README.md`

Phase 4:
Generate the shared helper files first:
- `db.py` using `psycopg2.connect(st.secrets["DB_URL"])`
- reusable query helpers
- reusable validation helpers
- reusable delete-confirmation helpers if useful

Phase 5:
Generate each Streamlit file one at a time in this order:
1. `streamlit_app.py`
2. `pages/1_Manage_Chemicals.py`
3. `pages/2_Manage_Warehouses_and_Locations.py`
4. `pages/3_Stock_In_Out_Management.py`
5. `pages/4_Inventory_Query.py`
6. `pages/5_Stocktake_Management.py`

For each file:
- output complete code
- use parameterized SQL only
- use dynamic dropdowns from database tables
- validate before database writes
- show friendly success/warning/error messages
- keep comments concise and useful
- make the page runnable as part of the overall app

Phase 6:
Generate:
- `requirements.txt`
- `README.md`
- a short `ai_prompts.md` template where I can paste the prompts and AI responses I used for the class submission

Output rules:
- Start with Phase 1 only.
- Do not generate everything at once.
- Do not skip directly to code.
- Be explicit and complete.
- Wait for my next message before moving to the next phase.


Continue to Phase 2 only.
Generate PostgreSQL DDL for all tables in the correct creation order.
Use IF NOT EXISTS where reasonable.
Include primary keys, foreign keys, unique constraints, check constraints, and ON DELETE behavior.
Also include a short explanation of why each table is created in that order.

Continue to Phase 3 only.
Generate the full Streamlit project structure following the conventions:
- root file: streamlit_app.py
- pages/ folder with numbered files
- requirements.txt
- helper modules
Show the file tree first, then explain the purpose of each file.

Continue to Phase 4 only.
Generate db.py first.
Requirements:
- import streamlit as st
- import psycopg2
- connection uses psycopg2.connect(st.secrets["DB_URL"])
- include helper functions for select, insert/update/delete, commit/rollback handling
- keep it simple enough for a college project
After db.py, generate validation.py.
Do not generate any page files yet.

Continue to Phase 5.
Generate streamlit_app.py only.
Requirements:
- use st.set_page_config()
- show title, welcome text, and instructions to use sidebar
- show dashboard metrics from the live database
- show recent stock document records
- use helper functions from db.py
- handle database errors gracefully
Do not generate other pages yet.