from db import run_select, get_lookup_options


def load_categories():
    """
    Load all categories for dropdown lists.
    Returns: list of tuples -> (id, category_name)
    """
    query = """
        SELECT
            id,
            category_name
        FROM categories
        ORDER BY category_name;
    """
    return get_lookup_options(query)


def load_active_warehouses():
    """
    Load active warehouses for dropdown lists.
    Returns: list of tuples -> (id, warehouse_name, warehouse_code)
    """
    query = """
        SELECT
            id,
            warehouse_name,
            warehouse_code
        FROM warehouses
        WHERE is_active = TRUE
        ORDER BY warehouse_name;
    """
    return get_lookup_options(query)


def load_active_chemicals():
    """
    Load active chemicals for dropdown lists.
    Returns: list of tuples -> (id, sku, chemical_name, unit)
    """
    query = """
        SELECT
            id,
            sku,
            chemical_name,
            unit
        FROM chemicals
        WHERE is_active = TRUE
        ORDER BY chemical_name;
    """
    return get_lookup_options(query)


def load_active_locations_by_warehouse(warehouse_id):
    """
    Load active storage locations for one warehouse.
    Returns: list of tuples -> (id, location_code, location_type)
    """
    query = """
        SELECT
            id,
            location_code,
            location_type
        FROM storage_locations
        WHERE warehouse_id = %s
          AND is_active = TRUE
        ORDER BY location_code;
    """
    return get_lookup_options(query, params=(warehouse_id,))


def get_dashboard_metrics():
    """
    Load dashboard metrics from the database.

    Returns:
        (success, result)
        result is a dictionary when success=True
    """
    total_chemicals_query = """
        SELECT COUNT(*)
        FROM chemicals
        WHERE is_active = TRUE;
    """

    total_warehouses_query = """
        SELECT COUNT(*)
        FROM warehouses
        WHERE is_active = TRUE;
    """

    total_inventory_query = """
        SELECT COALESCE(
            SUM(
                CASE
                    WHEN sd.doc_type = 'INBOUND' THEN sdi.quantity
                    WHEN sd.doc_type = 'OUTBOUND' THEN -sdi.quantity
                    ELSE 0
                END
            ),
            0
        )
        FROM stock_document_items sdi
        JOIN stock_documents sd
            ON sdi.document_id = sd.id;
    """

    low_stock_count_query = """
        SELECT COUNT(*)
        FROM (
            SELECT
                c.id,
                c.min_stock,
                COALESCE(
                    SUM(
                        CASE
                            WHEN sd.doc_type = 'INBOUND' THEN sdi.quantity
                            WHEN sd.doc_type = 'OUTBOUND' THEN -sdi.quantity
                            ELSE 0
                        END
                    ),
                    0
                ) AS on_hand_quantity
            FROM chemicals c
            LEFT JOIN stock_document_items sdi
                ON c.id = sdi.chemical_id
            LEFT JOIN stock_documents sd
                ON sdi.document_id = sd.id
            WHERE c.is_active = TRUE
            GROUP BY
                c.id,
                c.min_stock
        ) inventory_summary
        WHERE on_hand_quantity < min_stock;
    """

    success, total_chemicals = run_select(total_chemicals_query, fetchone=True)
    if not success:
        return False, "Unable to load total chemicals."

    success, total_warehouses = run_select(total_warehouses_query, fetchone=True)
    if not success:
        return False, "Unable to load total warehouses."

    success, total_inventory = run_select(total_inventory_query, fetchone=True)
    if not success:
        return False, "Unable to load total inventory quantity."

    success, low_stock_count = run_select(low_stock_count_query, fetchone=True)
    if not success:
        return False, "Unable to load low-stock item count."

    result = {
        "total_chemicals": total_chemicals[0] if total_chemicals else 0,
        "total_warehouses": total_warehouses[0] if total_warehouses else 0,
        "total_inventory_quantity": total_inventory[0] if total_inventory else 0,
        "low_stock_count": low_stock_count[0] if low_stock_count else 0,
    }
    return True, result


def get_recent_stock_documents(limit=10):
    """
    Load recent stock document records for the dashboard.
    """
    query = """
        SELECT
            sd.id,
            sd.doc_no,
            sd.doc_type,
            w.warehouse_name,
            sd.transaction_date,
            sd.operator_name,
            COALESCE(sd.counterparty_name, '') AS counterparty_name
        FROM stock_documents sd
        JOIN warehouses w
            ON sd.warehouse_id = w.id
        ORDER BY
            sd.transaction_date DESC,
            sd.id DESC
        LIMIT %s;
    """
    return run_select(query, params=(limit,))


def search_chemicals(sku_filter="", chemical_name_filter="", category_id=None):
    """
    Search chemical records with optional filters.
    """
    query = """
        SELECT
            c.id,
            c.sku,
            c.chemical_name,
            c.cas_no,
            c.specification,
            c.unit,
            c.hazard_level,
            c.category_id,
            COALESCE(cat.category_name, '') AS category_name,
            c.min_stock,
            c.is_active,
            c.created_at
        FROM chemicals c
        LEFT JOIN categories cat
            ON c.category_id = cat.id
        WHERE (%s = '' OR c.sku ILIKE %s)
          AND (%s = '' OR c.chemical_name ILIKE %s)
          AND (%s IS NULL OR c.category_id = %s)
        ORDER BY
            c.created_at DESC,
            c.id DESC;
    """

    sku_filter = str(sku_filter).strip()
    chemical_name_filter = str(chemical_name_filter).strip()

    params = (
        sku_filter,
        f"%{sku_filter}%",
        chemical_name_filter,
        f"%{chemical_name_filter}%",
        category_id,
        category_id,
    )
    return run_select(query, params=params)


def search_warehouses(name_filter="", code_filter=""):
    """
    Search warehouse records with optional filters.
    """
    query = """
        SELECT
            id,
            warehouse_name,
            warehouse_code,
            address,
            manager_name,
            is_active
        FROM warehouses
        WHERE (%s = '' OR warehouse_name ILIKE %s)
          AND (%s = '' OR warehouse_code ILIKE %s)
        ORDER BY warehouse_name;
    """

    name_filter = str(name_filter).strip()
    code_filter = str(code_filter).strip()

    params = (
        name_filter,
        f"%{name_filter}%",
        code_filter,
        f"%{code_filter}%",
    )
    return run_select(query, params=params)


def search_storage_locations(warehouse_id=None, location_code_filter=""):
    """
    Search storage location records with optional filters.
    """
    query = """
        SELECT
            sl.id,
            sl.warehouse_id,
            w.warehouse_name,
            w.warehouse_code,
            sl.location_code,
            sl.location_type,
            sl.capacity,
            sl.is_active
        FROM storage_locations sl
        JOIN warehouses w
            ON sl.warehouse_id = w.id
        WHERE (%s IS NULL OR sl.warehouse_id = %s)
          AND (%s = '' OR sl.location_code ILIKE %s)
        ORDER BY
            w.warehouse_name,
            sl.location_code;
    """

    location_code_filter = str(location_code_filter).strip()

    params = (
        warehouse_id,
        warehouse_id,
        location_code_filter,
        f"%{location_code_filter}%",
    )
    return run_select(query, params=params)


def search_stock_documents(
    doc_no_filter="",
    doc_type_filter="",
    warehouse_id=None,
    start_date=None,
    end_date=None,
):
    """
    Search stock document headers with optional filters.
    """
    query = """
        SELECT
            sd.id,
            sd.doc_no,
            sd.doc_type,
            w.warehouse_name,
            sd.transaction_date,
            sd.operator_name,
            COALESCE(sd.counterparty_name, '') AS counterparty_name,
            COALESCE(sd.notes, '') AS notes,
            COUNT(sdi.id) AS item_count,
            COALESCE(SUM(sdi.quantity), 0) AS total_quantity
        FROM stock_documents sd
        JOIN warehouses w
            ON sd.warehouse_id = w.id
        LEFT JOIN stock_document_items sdi
            ON sd.id = sdi.document_id
        WHERE (%s = '' OR sd.doc_no ILIKE %s)
          AND (%s = '' OR sd.doc_type = %s)
          AND (%s IS NULL OR sd.warehouse_id = %s)
          AND (%s IS NULL OR DATE(sd.transaction_date) >= %s)
          AND (%s IS NULL OR DATE(sd.transaction_date) <= %s)
        GROUP BY
            sd.id,
            sd.doc_no,
            sd.doc_type,
            w.warehouse_name,
            sd.transaction_date,
            sd.operator_name,
            sd.counterparty_name,
            sd.notes
        ORDER BY
            sd.transaction_date DESC,
            sd.id DESC;
    """

    doc_no_filter = str(doc_no_filter).strip()

    params = (
        doc_no_filter,
        f"%{doc_no_filter}%",
        doc_type_filter,
        doc_type_filter,
        warehouse_id,
        warehouse_id,
        start_date,
        start_date,
        end_date,
        end_date,
    )
    return run_select(query, params=params)


def get_stock_document_items(document_id):
    """
    Load item lines for one stock document.
    """
    query = """
        SELECT
            sdi.id,
            c.sku,
            c.chemical_name,
            sl.location_code,
            COALESCE(sdi.batch_no, '') AS batch_no,
            sdi.manufacture_date,
            sdi.expiry_date,
            sdi.quantity,
            sdi.unit_price,
            c.id AS chemical_id,
            sl.id AS location_id
        FROM stock_document_items sdi
        JOIN chemicals c
            ON sdi.chemical_id = c.id
        JOIN storage_locations sl
            ON sdi.location_id = sl.id
        WHERE sdi.document_id = %s
        ORDER BY sdi.id;
    """
    return run_select(query, params=(document_id,))


def get_available_stock(chemical_id, location_id, batch_no=None):
    """
    Calculate current available stock by chemical, location, and batch.
    """
    query = """
        SELECT COALESCE(
            SUM(
                CASE
                    WHEN sd.doc_type = 'INBOUND' THEN sdi.quantity
                    WHEN sd.doc_type = 'OUTBOUND' THEN -sdi.quantity
                    ELSE 0
                END
            ),
            0
        ) AS available_stock
        FROM stock_document_items sdi
        JOIN stock_documents sd
            ON sdi.document_id = sd.id
        WHERE sdi.chemical_id = %s
          AND sdi.location_id = %s
          AND COALESCE(sdi.batch_no, '') = COALESCE(%s, '');
    """

    success, result = run_select(
        query,
        params=(chemical_id, location_id, batch_no),
        fetchone=True,
    )

    if not success:
        return False, "Unable to calculate available stock."

    value = result[0] if result and result[0] is not None else 0
    return True, value


def get_inventory_rows(
    sku_filter="",
    chemical_name_filter="",
    warehouse_id=None,
    location_id=None,
    low_stock_only=False,
):
    """
    Load grouped inventory rows for the inventory query page.
    """
    query = """
        WITH inventory_base AS (
            SELECT
                c.id AS chemical_id,
                c.sku,
                c.chemical_name,
                c.unit,
                c.min_stock,
                w.id AS warehouse_id,
                w.warehouse_name,
                sl.id AS location_id,
                sl.location_code,
                COALESCE(sdi.batch_no, '') AS batch_no,
                sdi.manufacture_date,
                sdi.expiry_date,
                SUM(
                    CASE
                        WHEN sd.doc_type = 'INBOUND' THEN sdi.quantity
                        WHEN sd.doc_type = 'OUTBOUND' THEN -sdi.quantity
                        ELSE 0
                    END
                ) AS on_hand_quantity
            FROM stock_document_items sdi
            JOIN stock_documents sd
                ON sdi.document_id = sd.id
            JOIN chemicals c
                ON sdi.chemical_id = c.id
            JOIN storage_locations sl
                ON sdi.location_id = sl.id
            JOIN warehouses w
                ON sl.warehouse_id = w.id
            WHERE (%s = '' OR c.sku ILIKE %s)
              AND (%s = '' OR c.chemical_name ILIKE %s)
              AND (%s IS NULL OR w.id = %s)
              AND (%s IS NULL OR sl.id = %s)
            GROUP BY
                c.id,
                c.sku,
                c.chemical_name,
                c.unit,
                c.min_stock,
                w.id,
                w.warehouse_name,
                sl.id,
                sl.location_code,
                COALESCE(sdi.batch_no, ''),
                sdi.manufacture_date,
                sdi.expiry_date
        ),
        inventory_enriched AS (
            SELECT
                chemical_id,
                sku,
                chemical_name,
                unit,
                min_stock,
                warehouse_id,
                warehouse_name,
                location_id,
                location_code,
                batch_no,
                manufacture_date,
                expiry_date,
                on_hand_quantity,
                SUM(on_hand_quantity) OVER (
                    PARTITION BY chemical_id
                ) AS chemical_total_quantity
            FROM inventory_base
        )
        SELECT
            chemical_id,
            sku,
            chemical_name,
            unit,
            min_stock,
            warehouse_id,
            warehouse_name,
            location_id,
            location_code,
            batch_no,
            manufacture_date,
            expiry_date,
            on_hand_quantity,
            chemical_total_quantity,
            CASE
                WHEN chemical_total_quantity < min_stock THEN TRUE
                ELSE FALSE
            END AS is_low_stock
        FROM inventory_enriched
        WHERE on_hand_quantity <> 0
          AND (%s = FALSE OR chemical_total_quantity < min_stock)
        ORDER BY
            chemical_name,
            warehouse_name,
            location_code,
            batch_no;
    """

    sku_filter = str(sku_filter).strip()
    chemical_name_filter = str(chemical_name_filter).strip()

    params = (
        sku_filter,
        f"%{sku_filter}%",
        chemical_name_filter,
        f"%{chemical_name_filter}%",
        warehouse_id,
        warehouse_id,
        location_id,
        location_id,
        low_stock_only,
    )
    return run_select(query, params=params)


def get_inventory_summary(
    sku_filter="",
    chemical_name_filter="",
    warehouse_id=None,
    location_id=None,
    low_stock_only=False,
):
    """
    Load summary values for the inventory query page.
    """
    query = """
        WITH inventory_base AS (
            SELECT
                c.id AS chemical_id,
                c.min_stock,
                sdi.expiry_date,
                sl.id AS location_id,
                w.id AS warehouse_id,
                SUM(
                    CASE
                        WHEN sd.doc_type = 'INBOUND' THEN sdi.quantity
                        WHEN sd.doc_type = 'OUTBOUND' THEN -sdi.quantity
                        ELSE 0
                    END
                ) AS on_hand_quantity
            FROM stock_document_items sdi
            JOIN stock_documents sd
                ON sdi.document_id = sd.id
            JOIN chemicals c
                ON sdi.chemical_id = c.id
            JOIN storage_locations sl
                ON sdi.location_id = sl.id
            JOIN warehouses w
                ON sl.warehouse_id = w.id
            WHERE (%s = '' OR c.sku ILIKE %s)
              AND (%s = '' OR c.chemical_name ILIKE %s)
              AND (%s IS NULL OR w.id = %s)
              AND (%s IS NULL OR sl.id = %s)
            GROUP BY
                c.id,
                c.min_stock,
                sdi.expiry_date,
                sl.id,
                w.id
        ),
        enriched AS (
            SELECT
                chemical_id,
                min_stock,
                expiry_date,
                location_id,
                warehouse_id,
                on_hand_quantity,
                SUM(on_hand_quantity) OVER (
                    PARTITION BY chemical_id
                ) AS chemical_total_quantity
            FROM inventory_base
        ),
        filtered AS (
            SELECT *
            FROM enriched
            WHERE on_hand_quantity <> 0
              AND (%s = FALSE OR chemical_total_quantity < min_stock)
        )
        SELECT
            COUNT(*) AS inventory_row_count,
            COALESCE(SUM(on_hand_quantity), 0) AS total_on_hand_quantity,
            COUNT(DISTINCT chemical_id) FILTER (
                WHERE chemical_total_quantity < min_stock
            ) AS low_stock_chemical_count,
            COUNT(*) FILTER (
                WHERE expiry_date IS NOT NULL
                  AND expiry_date < CURRENT_DATE
            ) AS expired_batch_count
        FROM filtered;
    """

    sku_filter = str(sku_filter).strip()
    chemical_name_filter = str(chemical_name_filter).strip()

    params = (
        sku_filter,
        f"%{sku_filter}%",
        chemical_name_filter,
        f"%{chemical_name_filter}%",
        warehouse_id,
        warehouse_id,
        location_id,
        location_id,
        low_stock_only,
    )
    return run_select(query, params=params, fetchone=True)


def get_stocktake_sessions(
    warehouse_id=None,
    status_filter="",
    planned_date_from=None,
    planned_date_to=None,
):
    """
    Load stocktake session history with optional filters.
    """
    query = """
        SELECT
            ss.id,
            ss.session_name,
            w.warehouse_name,
            ss.planned_date,
            ss.completed_date,
            ss.status,
            ss.operator_name,
            COALESCE(ss.notes, '') AS notes,
            COUNT(si.id) AS item_count
        FROM stocktake_sessions ss
        JOIN warehouses w
            ON ss.warehouse_id = w.id
        LEFT JOIN stocktake_items si
            ON ss.id = si.session_id
        WHERE (%s IS NULL OR ss.warehouse_id = %s)
          AND (%s = '' OR ss.status = %s)
          AND (%s IS NULL OR ss.planned_date >= %s)
          AND (%s IS NULL OR ss.planned_date <= %s)
        GROUP BY
            ss.id,
            ss.session_name,
            w.warehouse_name,
            ss.planned_date,
            ss.completed_date,
            ss.status,
            ss.operator_name,
            ss.notes
        ORDER BY
            ss.planned_date DESC,
            ss.id DESC;
    """

    params = (
        warehouse_id,
        warehouse_id,
        status_filter,
        status_filter,
        planned_date_from,
        planned_date_from,
        planned_date_to,
        planned_date_to,
    )
    return run_select(query, params=params)


def get_stocktake_items(session_id):
    """
    Load stocktake item lines for one session.
    """
    query = """
        SELECT
            si.id,
            c.sku,
            c.chemical_name,
            sl.location_code,
            COALESCE(si.batch_no, '') AS batch_no,
            si.system_quantity,
            si.counted_quantity,
            (si.counted_quantity - si.system_quantity) AS variance,
            c.id AS chemical_id,
            sl.id AS location_id
        FROM stocktake_items si
        JOIN chemicals c
            ON si.chemical_id = c.id
        JOIN storage_locations sl
            ON si.location_id = sl.id
        WHERE si.session_id = %s
        ORDER BY si.id;
    """
    return run_select(query, params=(session_id,))


def get_system_quantity(chemical_id, location_id, batch_no=None):
    """
    Calculate system quantity for stocktake comparison.
    """
    query = """
        SELECT COALESCE(
            SUM(
                CASE
                    WHEN sd.doc_type = 'INBOUND' THEN sdi.quantity
                    WHEN sd.doc_type = 'OUTBOUND' THEN -sdi.quantity
                    ELSE 0
                END
            ),
            0
        ) AS system_quantity
        FROM stock_document_items sdi
        JOIN stock_documents sd
            ON sdi.document_id = sd.id
        WHERE sdi.chemical_id = %s
          AND sdi.location_id = %s
          AND COALESCE(sdi.batch_no, '') = COALESCE(%s, '');
    """

    success, result = run_select(
        query,
        params=(chemical_id, location_id, batch_no),
        fetchone=True,
    )

    if not success:
        return False, "Unable to calculate system quantity."

    value = result[0] if result and result[0] is not None else 0
    return True, value