import streamlit as st
from db import run_select, run_action, value_exists, get_lookup_options
from validation import validate_warehouse_form, validate_location_form, add_unique_error


def clean_text(value):
    """
    Convert blank text to None after stripping whitespace.
    """
    if value is None:
        return None
    text = str(value).strip()
    return text if text != "" else None


def show_validation_errors(errors):
    """
    Show all validation errors together.
    """
    for error in errors:
        st.error(error)


def load_warehouses():
    """
    Load all warehouses for dropdowns and tables.
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
        ORDER BY warehouse_name;
    """
    return get_lookup_options(query)


def load_warehouse_table(search_name="", search_code=""):
    """
    Load warehouse records with optional filters.
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
    search_name = search_name.strip()
    search_code = search_code.strip()

    params = (
        search_name,
        f"%{search_name}%",
        search_code,
        f"%{search_code}%"
    )

    success, result = run_select(query, params=params)
    if not success:
        return None, result
    return result, None


def load_location_table(warehouse_id=None, search_location_code=""):
    """
    Load storage locations with optional filters.
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
        JOIN warehouses w ON sl.warehouse_id = w.id
        WHERE (%s IS NULL OR sl.warehouse_id = %s)
          AND (%s = '' OR sl.location_code ILIKE %s)
        ORDER BY w.warehouse_name, sl.location_code;
    """

    search_location_code = search_location_code.strip()

    params = (
        warehouse_id,
        warehouse_id,
        search_location_code,
        f"%{search_location_code}%"
    )

    success, result = run_select(query, params=params)
    if not success:
        return None, result
    return result, None


def get_warehouse_by_id(warehouse_id):
    """
    Get one warehouse by ID.
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
        WHERE id = %s;
    """
    success, result = run_select(query, params=(warehouse_id,), fetchone=True)
    if not success:
        return None, result
    return result, None


def get_location_by_id(location_id):
    """
    Get one storage location by ID.
    """
    query = """
        SELECT
            id,
            warehouse_id,
            location_code,
            location_type,
            capacity,
            is_active
        FROM storage_locations
        WHERE id = %s;
    """
    success, result = run_select(query, params=(location_id,), fetchone=True)
    if not success:
        return None, result
    return result, None


def warehouse_name_exists(warehouse_name, exclude_id=None):
    """
    Check if warehouse name already exists.
    """
    if exclude_id is None:
        query = """
            SELECT 1
            FROM warehouses
            WHERE LOWER(warehouse_name) = LOWER(%s);
        """
        return value_exists(query, params=(warehouse_name,))
    else:
        query = """
            SELECT 1
            FROM warehouses
            WHERE LOWER(warehouse_name) = LOWER(%s)
              AND id <> %s;
        """
        return value_exists(query, params=(warehouse_name, exclude_id))


def warehouse_code_exists(warehouse_code, exclude_id=None):
    """
    Check if warehouse code already exists.
    """
    if exclude_id is None:
        query = """
            SELECT 1
            FROM warehouses
            WHERE LOWER(warehouse_code) = LOWER(%s);
        """
        return value_exists(query, params=(warehouse_code,))
    else:
        query = """
            SELECT 1
            FROM warehouses
            WHERE LOWER(warehouse_code) = LOWER(%s)
              AND id <> %s;
        """
        return value_exists(query, params=(warehouse_code, exclude_id))


def location_code_exists_in_warehouse(warehouse_id, location_code, exclude_id=None):
    """
    Check if location code already exists within the same warehouse.
    """
    if exclude_id is None:
        query = """
            SELECT 1
            FROM storage_locations
            WHERE warehouse_id = %s
              AND LOWER(location_code) = LOWER(%s);
        """
        return value_exists(query, params=(warehouse_id, location_code))
    else:
        query = """
            SELECT 1
            FROM storage_locations
            WHERE warehouse_id = %s
              AND LOWER(location_code) = LOWER(%s)
              AND id <> %s;
        """
        return value_exists(query, params=(warehouse_id, location_code, exclude_id))


def format_warehouse_label(row):
    """
    User-friendly warehouse label for selectboxes.
    """
    return f"{row[1]} ({row[2]})"


st.title("Manage Warehouses and Locations")
st.write("Add, view, edit, and delete warehouse and storage location records.")

warehouse_rows = load_warehouses()

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    [
        "Add Warehouse",
        "Add Location",
        "View / Search Records",
        "Edit Warehouse",
        "Edit Location",
        "Delete Records"
    ]
)

# ---------------------------------------------------------
# Tab 1: Add Warehouse
# ---------------------------------------------------------
with tab1:
    st.subheader("Add New Warehouse")

    with st.form("add_warehouse_form"):
        col1, col2 = st.columns(2)

        with col1:
            warehouse_name = st.text_input("Warehouse Name *")
            warehouse_code = st.text_input("Warehouse Code *")
            address = st.text_input("Address")

        with col2:
            manager_name = st.text_input("Manager Name")
            is_active = st.checkbox("Is Active", value=True)

        submitted = st.form_submit_button("Add Warehouse")

        if submitted:
            errors = validate_warehouse_form(warehouse_name, warehouse_code)

            cleaned_name = clean_text(warehouse_name)
            cleaned_code = clean_text(warehouse_code)

            if cleaned_name and warehouse_name_exists(cleaned_name):
                add_unique_error(errors, True, "Warehouse name")

            if cleaned_code and warehouse_code_exists(cleaned_code):
                add_unique_error(errors, True, "Warehouse code")

            if errors:
                show_validation_errors(errors)
            else:
                query = """
                    INSERT INTO warehouses
                    (
                        warehouse_name,
                        warehouse_code,
                        address,
                        manager_name,
                        is_active
                    )
                    VALUES (%s, %s, %s, %s, %s);
                """
                params = (
                    cleaned_name,
                    cleaned_code,
                    clean_text(address),
                    clean_text(manager_name),
                    is_active
                )

                success, result = run_action(query, params=params)

                if success:
                    st.success("Warehouse added successfully.")
                    st.rerun()
                else:
                    st.error(result)

# ---------------------------------------------------------
# Tab 2: Add Location
# ---------------------------------------------------------
with tab2:
    st.subheader("Add New Storage Location")

    if not warehouse_rows:
        st.warning("Please add a warehouse first before adding storage locations.")
    else:
        warehouse_options = {row[0]: format_warehouse_label(row) for row in warehouse_rows}

        with st.form("add_location_form"):
            col1, col2 = st.columns(2)

            with col1:
                selected_warehouse_id = st.selectbox(
                    "Warehouse *",
                    options=list(warehouse_options.keys()),
                    format_func=lambda x: warehouse_options[x]
                )
                location_code = st.text_input("Location Code *")
                location_type = st.text_input("Location Type")

            with col2:
                capacity = st.number_input("Capacity", min_value=0.0, value=0.0, step=0.01)
                is_active = st.checkbox("Is Active", value=True)

            location_submitted = st.form_submit_button("Add Location")

            if location_submitted:
                errors = validate_location_form(location_code, capacity)

                cleaned_location_code = clean_text(location_code)

                if selected_warehouse_id is None:
                    errors.append("Warehouse is required.")

                if cleaned_location_code and selected_warehouse_id is not None:
                    if location_code_exists_in_warehouse(selected_warehouse_id, cleaned_location_code):
                        errors.append("Location code already exists in the selected warehouse.")

                if errors:
                    show_validation_errors(errors)
                else:
                    query = """
                        INSERT INTO storage_locations
                        (
                            warehouse_id,
                            location_code,
                            location_type,
                            capacity,
                            is_active
                        )
                        VALUES (%s, %s, %s, %s, %s);
                    """
                    params = (
                        selected_warehouse_id,
                        cleaned_location_code,
                        clean_text(location_type),
                        capacity,
                        is_active
                    )

                    success, result = run_action(query, params=params)

                    if success:
                        st.success("Storage location added successfully.")
                        st.rerun()
                    else:
                        st.error(result)

# ---------------------------------------------------------
# Tab 3: View / Search Records
# ---------------------------------------------------------
with tab3:
    st.subheader("View and Search Warehouses")

    col1, col2 = st.columns(2)
    with col1:
        warehouse_name_filter = st.text_input("Search Warehouse Name", key="warehouse_name_filter")
    with col2:
        warehouse_code_filter = st.text_input("Search Warehouse Code", key="warehouse_code_filter")

    warehouse_table_rows, warehouse_table_error = load_warehouse_table(
        search_name=warehouse_name_filter,
        search_code=warehouse_code_filter
    )

    if warehouse_table_error:
        st.error(f"Unable to load warehouse records. {warehouse_table_error}")
    else:
        if warehouse_table_rows:
            warehouse_display = []
            for row in warehouse_table_rows:
                warehouse_display.append(
                    {
                        "ID": row[0],
                        "Warehouse Name": row[1],
                        "Warehouse Code": row[2],
                        "Address": row[3],
                        "Manager Name": row[4],
                        "Is Active": row[5]
                    }
                )
            st.dataframe(warehouse_display, use_container_width=True)
        else:
            st.info("No warehouse records matched the current filters.")

    st.subheader("View and Search Storage Locations")

    location_filter_col1, location_filter_col2 = st.columns(2)

    warehouse_filter_options = [None]
    warehouse_filter_map = {None: "-- All Warehouses --"}
    for row in warehouse_rows:
        warehouse_filter_options.append(row[0])
        warehouse_filter_map[row[0]] = format_warehouse_label(row)

    with location_filter_col1:
        selected_filter_warehouse = st.selectbox(
            "Filter by Warehouse",
            options=warehouse_filter_options,
            format_func=lambda x: warehouse_filter_map[x],
            key="selected_filter_warehouse"
        )

    with location_filter_col2:
        location_code_filter = st.text_input("Search Location Code", key="location_code_filter")

    location_rows, location_error = load_location_table(
        warehouse_id=selected_filter_warehouse,
        search_location_code=location_code_filter
    )

    if location_error:
        st.error(f"Unable to load storage locations. {location_error}")
    else:
        if location_rows:
            location_display = []
            for row in location_rows:
                location_display.append(
                    {
                        "ID": row[0],
                        "Warehouse Name": row[2],
                        "Warehouse Code": row[3],
                        "Location Code": row[4],
                        "Location Type": row[5],
                        "Capacity": row[6],
                        "Is Active": row[7]
                    }
                )
            st.dataframe(location_display, use_container_width=True)
        else:
            st.info("No storage location records matched the current filters.")

# ---------------------------------------------------------
# Tab 4: Edit Warehouse
# ---------------------------------------------------------
with tab4:
    st.subheader("Edit Warehouse")

    if not warehouse_rows:
        st.info("No warehouse records are available to edit.")
    else:
        warehouse_options = {row[0]: format_warehouse_label(row) for row in warehouse_rows}

        selected_warehouse_id = st.selectbox(
            "Select Warehouse to Edit",
            options=list(warehouse_options.keys()),
            format_func=lambda x: warehouse_options[x],
            key="edit_warehouse_id"
        )

        warehouse_record, warehouse_error = get_warehouse_by_id(selected_warehouse_id)

        if warehouse_error:
            st.error(f"Unable to load warehouse details. {warehouse_error}")
        elif warehouse_record:
            with st.form("edit_warehouse_form"):
                col1, col2 = st.columns(2)

                with col1:
                    edit_warehouse_name = st.text_input("Warehouse Name *", value=warehouse_record[1])
                    edit_warehouse_code = st.text_input("Warehouse Code *", value=warehouse_record[2])
                    edit_address = st.text_input("Address", value=warehouse_record[3] or "")

                with col2:
                    edit_manager_name = st.text_input("Manager Name", value=warehouse_record[4] or "")
                    edit_is_active = st.checkbox("Is Active", value=warehouse_record[5])

                update_warehouse_submitted = st.form_submit_button("Update Warehouse")

                if update_warehouse_submitted:
                    errors = validate_warehouse_form(edit_warehouse_name, edit_warehouse_code)

                    cleaned_name = clean_text(edit_warehouse_name)
                    cleaned_code = clean_text(edit_warehouse_code)

                    if cleaned_name and warehouse_name_exists(cleaned_name, exclude_id=selected_warehouse_id):
                        add_unique_error(errors, True, "Warehouse name")

                    if cleaned_code and warehouse_code_exists(cleaned_code, exclude_id=selected_warehouse_id):
                        add_unique_error(errors, True, "Warehouse code")

                    if errors:
                        show_validation_errors(errors)
                    else:
                        query = """
                            UPDATE warehouses
                            SET
                                warehouse_name = %s,
                                warehouse_code = %s,
                                address = %s,
                                manager_name = %s,
                                is_active = %s
                            WHERE id = %s;
                        """
                        params = (
                            cleaned_name,
                            cleaned_code,
                            clean_text(edit_address),
                            clean_text(edit_manager_name),
                            edit_is_active,
                            selected_warehouse_id
                        )

                        success, result = run_action(query, params=params)

                        if success:
                            st.success("Warehouse updated successfully.")
                            st.rerun()
                        else:
                            st.error(result)

# ---------------------------------------------------------
# Tab 5: Edit Location
# ---------------------------------------------------------
with tab5:
    st.subheader("Edit Storage Location")

    if not warehouse_rows:
        st.info("No warehouses are available.")
    else:
        edit_location_warehouse_id = st.selectbox(
            "Select Warehouse",
            options=[row[0] for row in warehouse_rows],
            format_func=lambda x: {row[0]: format_warehouse_label(row) for row in warehouse_rows}[x],
            key="edit_location_warehouse_select"
        )

        warehouse_locations, warehouse_locations_error = load_location_table(
            warehouse_id=edit_location_warehouse_id
        )

        if warehouse_locations_error:
            st.error(f"Unable to load locations for the selected warehouse. {warehouse_locations_error}")
        elif not warehouse_locations:
            st.info("No locations exist for the selected warehouse.")
        else:
            location_options = {
                row[0]: f"{row[4]} ({row[5] or 'No Type'})"
                for row in warehouse_locations
            }

            selected_location_id = st.selectbox(
                "Select Location to Edit",
                options=list(location_options.keys()),
                format_func=lambda x: location_options[x],
                key="selected_location_id_edit"
            )

            location_record, location_record_error = get_location_by_id(selected_location_id)

            if location_record_error:
                st.error(f"Unable to load location details. {location_record_error}")
            elif location_record:
                warehouse_options = {row[0]: format_warehouse_label(row) for row in warehouse_rows}

                with st.form("edit_location_form"):
                    col1, col2 = st.columns(2)

                    with col1:
                        edit_location_warehouse_id_value = st.selectbox(
                            "Warehouse *",
                            options=list(warehouse_options.keys()),
                            index=list(warehouse_options.keys()).index(location_record[1]),
                            format_func=lambda x: warehouse_options[x]
                        )
                        edit_location_code = st.text_input("Location Code *", value=location_record[2])
                        edit_location_type = st.text_input("Location Type", value=location_record[3] or "")

                    with col2:
                        edit_capacity = st.number_input(
                            "Capacity",
                            min_value=0.0,
                            value=float(location_record[4] or 0),
                            step=0.01
                        )
                        edit_location_is_active = st.checkbox("Is Active", value=location_record[5])

                    update_location_submitted = st.form_submit_button("Update Location")

                    if update_location_submitted:
                        errors = validate_location_form(edit_location_code, edit_capacity)

                        cleaned_location_code = clean_text(edit_location_code)

                        if edit_location_warehouse_id_value is None:
                            errors.append("Warehouse is required.")

                        if cleaned_location_code and edit_location_warehouse_id_value is not None:
                            if location_code_exists_in_warehouse(
                                edit_location_warehouse_id_value,
                                cleaned_location_code,
                                exclude_id=selected_location_id
                            ):
                                errors.append("Location code already exists in the selected warehouse.")

                        if errors:
                            show_validation_errors(errors)
                        else:
                            query = """
                                UPDATE storage_locations
                                SET
                                    warehouse_id = %s,
                                    location_code = %s,
                                    location_type = %s,
                                    capacity = %s,
                                    is_active = %s
                                WHERE id = %s;
                            """
                            params = (
                                edit_location_warehouse_id_value,
                                cleaned_location_code,
                                clean_text(edit_location_type),
                                edit_capacity,
                                edit_location_is_active,
                                selected_location_id
                            )

                            success, result = run_action(query, params=params)

                            if success:
                                st.success("Storage location updated successfully.")
                                st.rerun()
                            else:
                                st.error(result)

# ---------------------------------------------------------
# Tab 6: Delete Records
# ---------------------------------------------------------
with tab6:
    st.subheader("Delete Warehouse")
    st.warning("Delete actions are permanent. Please confirm before continuing.")

    if not warehouse_rows:
        st.info("No warehouse records are available to delete.")
    else:
        warehouse_options = {row[0]: format_warehouse_label(row) for row in warehouse_rows}

        selected_delete_warehouse_id = st.selectbox(
            "Select Warehouse to Delete",
            options=list(warehouse_options.keys()),
            format_func=lambda x: warehouse_options[x],
            key="delete_warehouse_id"
        )

        delete_warehouse_record, delete_warehouse_error = get_warehouse_by_id(selected_delete_warehouse_id)

        if delete_warehouse_error:
            st.error(f"Unable to load warehouse details. {delete_warehouse_error}")
        elif delete_warehouse_record:
            st.write(f"**Warehouse Name:** {delete_warehouse_record[1]}")
            st.write(f"**Warehouse Code:** {delete_warehouse_record[2]}")
            st.write(f"**Address:** {delete_warehouse_record[3] or ''}")
            st.write(f"**Manager Name:** {delete_warehouse_record[4] or ''}")

            confirm_delete_warehouse = st.checkbox(
                "I confirm that I want to delete this warehouse.",
                key="confirm_delete_warehouse"
            )

            if st.button("Delete Warehouse", key="delete_warehouse_button"):
                if not confirm_delete_warehouse:
                    st.error("Please confirm deletion before deleting the warehouse.")
                else:
                    query = """
                        DELETE FROM warehouses
                        WHERE id = %s;
                    """
                    success, result = run_action(query, params=(selected_delete_warehouse_id,))

                    if success:
                        if result > 0:
                            st.success("Warehouse deleted successfully.")
                            st.rerun()
                        else:
                            st.warning("No warehouse record was deleted.")
                    else:
                        st.error(result)

    st.divider()
    st.subheader("Delete Storage Location")

    if not warehouse_rows:
        st.info("No warehouses are available.")
    else:
        delete_location_warehouse_id = st.selectbox(
            "Select Warehouse for Location Deletion",
            options=[row[0] for row in warehouse_rows],
            format_func=lambda x: {row[0]: format_warehouse_label(row) for row in warehouse_rows}[x],
            key="delete_location_warehouse_select"
        )

        delete_locations, delete_locations_error = load_location_table(
            warehouse_id=delete_location_warehouse_id
        )

        if delete_locations_error:
            st.error(f"Unable to load storage locations. {delete_locations_error}")
        elif not delete_locations:
            st.info("No storage locations exist for the selected warehouse.")
        else:
            delete_location_options = {
                row[0]: f"{row[4]} ({row[5] or 'No Type'})"
                for row in delete_locations
            }

            selected_delete_location_id = st.selectbox(
                "Select Location to Delete",
                options=list(delete_location_options.keys()),
                format_func=lambda x: delete_location_options[x],
                key="selected_delete_location_id"
            )

            delete_location_record, delete_location_record_error = get_location_by_id(selected_delete_location_id)

            if delete_location_record_error:
                st.error(f"Unable to load selected location details. {delete_location_record_error}")
            elif delete_location_record:
                st.write(f"**Location Code:** {delete_location_record[2]}")
                st.write(f"**Location Type:** {delete_location_record[3] or ''}")
                st.write(f"**Capacity:** {delete_location_record[4]}")
                st.write(f"**Is Active:** {delete_location_record[5]}")

                confirm_delete_location = st.checkbox(
                    "I confirm that I want to delete this storage location.",
                    key="confirm_delete_location"
                )

                if st.button("Delete Storage Location", key="delete_location_button"):
                    if not confirm_delete_location:
                        st.error("Please confirm deletion before deleting the storage location.")
                    else:
                        query = """
                            DELETE FROM storage_locations
                            WHERE id = %s;
                        """
                        success, result = run_action(query, params=(selected_delete_location_id,))

                        if success:
                            if result > 0:
                                st.success("Storage location deleted successfully.")
                                st.rerun()
                            else:
                                st.warning("No storage location record was deleted.")
                        else:
                            st.error(result)