import streamlit as st
from db import run_select, run_action, value_exists, get_lookup_options
from validation import validate_chemical_form, add_unique_error


def clean_text(value):
    """
    Convert empty strings to None after stripping whitespace.
    """
    if value is None:
        return None
    text = str(value).strip()
    return text if text != "" else None


def show_validation_errors(errors):
    """
    Display all validation errors together.
    """
    if errors:
        for error in errors:
            st.error(error)


def load_categories():
    """
    Load category dropdown options from the database.
    """
    query = """
        SELECT id, category_name
        FROM categories
        ORDER BY category_name;
    """
    return get_lookup_options(query)


def get_category_map():
    """
    Return a dictionary like {id: category_name}.
    """
    rows = load_categories()
    category_map = {None: "-- No Category --"}
    for row in rows:
        category_map[row[0]] = row[1]
    return category_map


def load_chemicals(sku_filter="", name_filter="", category_filter=None):
    """
    Load chemicals with optional search filters.
    Uses parameterized SQL only.
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
        LEFT JOIN categories cat ON c.category_id = cat.id
        WHERE (%s = '' OR c.sku ILIKE %s)
          AND (%s = '' OR c.chemical_name ILIKE %s)
          AND (%s IS NULL OR c.category_id = %s)
        ORDER BY c.created_at DESC, c.id DESC;
    """

    sku_filter = sku_filter.strip()
    name_filter = name_filter.strip()

    params = (
        sku_filter,
        f"%{sku_filter}%",
        name_filter,
        f"%{name_filter}%",
        category_filter,
        category_filter,
    )

    success, result = run_select(query, params=params)
    if not success:
        return None, result
    return result, None


def get_chemical_by_id(chemical_id):
    """
    Load one chemical record by ID.
    """
    query = """
        SELECT
            id,
            sku,
            chemical_name,
            cas_no,
            specification,
            unit,
            hazard_level,
            category_id,
            min_stock,
            is_active
        FROM chemicals
        WHERE id = %s;
    """
    success, result = run_select(query, params=(chemical_id,), fetchone=True)
    if not success:
        return None, result
    return result, None


def chemical_sku_exists(sku, exclude_id=None):
    """
    Check whether the SKU already exists.
    """
    if exclude_id is None:
        query = """
            SELECT 1
            FROM chemicals
            WHERE LOWER(sku) = LOWER(%s);
        """
        return value_exists(query, params=(sku,))
    else:
        query = """
            SELECT 1
            FROM chemicals
            WHERE LOWER(sku) = LOWER(%s)
              AND id <> %s;
        """
        return value_exists(query, params=(sku, exclude_id))


def format_chemical_label(row):
    """
    Build a user-friendly label for select boxes.
    """
    return f"{row[1]} - {row[2]}"


st.title("Manage Chemicals")
st.write("Add, search, edit, and delete chemical master data records.")

category_rows = load_categories()
category_map = {None: "-- No Category --"}
for row in category_rows:
    category_map[row[0]] = row[1]

all_chemicals, all_chemicals_error = load_chemicals()

if all_chemicals_error:
    st.error(f"Unable to load chemicals. {all_chemicals_error}")
    all_chemicals = []

tab1, tab2, tab3, tab4 = st.tabs(
    ["Add Chemical", "View / Search Chemicals", "Edit Chemical", "Delete Chemical"]
)

# ---------------------------------------------------------
# Tab 1: Add Chemical
# ---------------------------------------------------------
with tab1:
    st.subheader("Add New Chemical")

    with st.form("add_chemical_form"):
        col1, col2 = st.columns(2)

        with col1:
            sku = st.text_input("SKU *")
            chemical_name = st.text_input("Chemical Name *")
            cas_no = st.text_input("CAS No")
            specification = st.text_input("Specification")

        with col2:
            unit = st.text_input("Unit *")
            hazard_level = st.text_input("Hazard Level")
            category_id = st.selectbox(
                "Category",
                options=list(category_map.keys()),
                format_func=lambda x: category_map.get(x, "-- No Category --"),
            )
            min_stock = st.number_input("Minimum Stock", min_value=0.0, value=0.0, step=0.01)

        is_active = st.checkbox("Is Active", value=True)

        submitted = st.form_submit_button("Add Chemical")

        if submitted:
            errors = validate_chemical_form(sku, chemical_name, unit, min_stock)

            cleaned_sku = clean_text(sku)
            cleaned_name = clean_text(chemical_name)
            cleaned_unit = clean_text(unit)

            if cleaned_sku and chemical_sku_exists(cleaned_sku):
                add_unique_error(errors, True, "SKU")

            if errors:
                show_validation_errors(errors)
            else:
                insert_query = """
                    INSERT INTO chemicals
                    (
                        sku,
                        chemical_name,
                        cas_no,
                        specification,
                        unit,
                        hazard_level,
                        category_id,
                        min_stock,
                        is_active
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                """

                params = (
                    cleaned_sku,
                    cleaned_name,
                    clean_text(cas_no),
                    clean_text(specification),
                    cleaned_unit,
                    clean_text(hazard_level),
                    category_id,
                    min_stock,
                    is_active,
                )

                success, result = run_action(insert_query, params=params)

                if success:
                    st.success("Chemical record added successfully.")
                    st.rerun()
                else:
                    st.error(result)

# ---------------------------------------------------------
# Tab 2: View / Search Chemicals
# ---------------------------------------------------------
with tab2:
    st.subheader("Search and View Chemicals")

    col1, col2, col3 = st.columns(3)

    with col1:
        search_sku = st.text_input("Search by SKU", key="search_sku")

    with col2:
        search_name = st.text_input("Search by Chemical Name", key="search_name")

    with col3:
        search_category = st.selectbox(
            "Filter by Category",
            options=list(category_map.keys()),
            format_func=lambda x: category_map.get(x, "-- All Categories --") if x is not None else "-- All Categories --",
            key="search_category",
        )

    filtered_category = None if search_category is None else search_category
    filtered_rows, filtered_error = load_chemicals(
        sku_filter=search_sku,
        name_filter=search_name,
        category_filter=filtered_category,
    )

    if filtered_error:
        st.error(f"Unable to search chemicals. {filtered_error}")
    else:
        if filtered_rows:
            display_rows = []
            for row in filtered_rows:
                display_rows.append(
                    {
                        "ID": row[0],
                        "SKU": row[1],
                        "Chemical Name": row[2],
                        "CAS No": row[3],
                        "Specification": row[4],
                        "Unit": row[5],
                        "Hazard Level": row[6],
                        "Category": row[8],
                        "Minimum Stock": row[9],
                        "Is Active": row[10],
                        "Created At": row[11],
                    }
                )

            st.dataframe(display_rows, use_container_width=True)
            st.caption(f"Total records found: {len(display_rows)}")
        else:
            st.warning("No chemical records matched the current filters.")

# ---------------------------------------------------------
# Tab 3: Edit Chemical
# ---------------------------------------------------------
with tab3:
    st.subheader("Edit Chemical Record")

    if not all_chemicals:
        st.info("No chemical records are available to edit.")
    else:
        chemical_options = {row[0]: format_chemical_label(row) for row in all_chemicals}

        selected_edit_id = st.selectbox(
            "Select a chemical to edit",
            options=list(chemical_options.keys()),
            format_func=lambda x: chemical_options[x],
            key="edit_chemical_id",
        )

        selected_row, selected_error = get_chemical_by_id(selected_edit_id)

        if selected_error:
            st.error(f"Unable to load the selected chemical. {selected_error}")
        elif selected_row:
            with st.form("edit_chemical_form"):
                col1, col2 = st.columns(2)

                with col1:
                    edit_sku = st.text_input("SKU *", value=selected_row[1])
                    edit_chemical_name = st.text_input("Chemical Name *", value=selected_row[2])
                    edit_cas_no = st.text_input("CAS No", value=selected_row[3] or "")
                    edit_specification = st.text_input("Specification", value=selected_row[4] or "")

                with col2:
                    edit_unit = st.text_input("Unit *", value=selected_row[5])
                    edit_hazard_level = st.text_input("Hazard Level", value=selected_row[6] or "")
                    edit_category_id = st.selectbox(
                        "Category",
                        options=list(category_map.keys()),
                        index=list(category_map.keys()).index(selected_row[7]) if selected_row[7] in category_map else 0,
                        format_func=lambda x: category_map.get(x, "-- No Category --"),
                    )
                    edit_min_stock = st.number_input(
                        "Minimum Stock",
                        min_value=0.0,
                        value=float(selected_row[8]),
                        step=0.01,
                    )

                edit_is_active = st.checkbox("Is Active", value=selected_row[9])

                update_submitted = st.form_submit_button("Update Chemical")

                if update_submitted:
                    errors = validate_chemical_form(
                        edit_sku,
                        edit_chemical_name,
                        edit_unit,
                        edit_min_stock,
                    )

                    cleaned_edit_sku = clean_text(edit_sku)
                    cleaned_edit_name = clean_text(edit_chemical_name)
                    cleaned_edit_unit = clean_text(edit_unit)

                    if cleaned_edit_sku and chemical_sku_exists(cleaned_edit_sku, exclude_id=selected_edit_id):
                        add_unique_error(errors, True, "SKU")

                    if errors:
                        show_validation_errors(errors)
                    else:
                        update_query = """
                            UPDATE chemicals
                            SET
                                sku = %s,
                                chemical_name = %s,
                                cas_no = %s,
                                specification = %s,
                                unit = %s,
                                hazard_level = %s,
                                category_id = %s,
                                min_stock = %s,
                                is_active = %s
                            WHERE id = %s;
                        """

                        params = (
                            cleaned_edit_sku,
                            cleaned_edit_name,
                            clean_text(edit_cas_no),
                            clean_text(edit_specification),
                            cleaned_edit_unit,
                            clean_text(edit_hazard_level),
                            edit_category_id,
                            edit_min_stock,
                            edit_is_active,
                            selected_edit_id,
                        )

                        success, result = run_action(update_query, params=params)

                        if success:
                            st.success("Chemical record updated successfully.")
                            st.rerun()
                        else:
                            st.error(result)

# ---------------------------------------------------------
# Tab 4: Delete Chemical
# ---------------------------------------------------------
with tab4:
    st.subheader("Delete Chemical Record")

    if not all_chemicals:
        st.info("No chemical records are available to delete.")
    else:
        chemical_options = {row[0]: format_chemical_label(row) for row in all_chemicals}

        selected_delete_id = st.selectbox(
            "Select a chemical to delete",
            options=list(chemical_options.keys()),
            format_func=lambda x: chemical_options[x],
            key="delete_chemical_id",
        )

        delete_row, delete_error = get_chemical_by_id(selected_delete_id)

        if delete_error:
            st.error(f"Unable to load the selected chemical. {delete_error}")
        elif delete_row:
            st.warning("Deleting a chemical is permanent. Please confirm before continuing.")

            st.write(f"**SKU:** {delete_row[1]}")
            st.write(f"**Chemical Name:** {delete_row[2]}")
            st.write(f"**Unit:** {delete_row[5]}")
            st.write(f"**Minimum Stock:** {delete_row[8]}")

            confirm_delete = st.checkbox(
                "I confirm that I want to delete this chemical record.",
                key="confirm_delete_chemical",
            )

            if st.button("Delete Chemical", key="delete_chemical_button"):
                if not confirm_delete:
                    st.error("Please confirm deletion before deleting the record.")
                else:
                    delete_query = """
                        DELETE FROM chemicals
                        WHERE id = %s;
                    """
                    success, result = run_action(delete_query, params=(selected_delete_id,))

                    if success:
                        if result > 0:
                            st.success("Chemical record deleted successfully.")
                            st.rerun()
                        else:
                            st.warning("No record was deleted.")
                    else:
                        st.error(result)