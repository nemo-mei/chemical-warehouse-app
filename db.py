import streamlit as st
import psycopg2
from psycopg2 import Error


def get_connection():
    """
    Create and return a new PostgreSQL connection using Streamlit secrets.
    """
    return psycopg2.connect(st.secrets["DB_URL"])


def run_select(query, params=None, fetchone=False):
    """
    Run a SELECT query.

    Args:
        query (str): SQL query with %s placeholders
        params (tuple | list | None): Query parameters
        fetchone (bool): If True, return one row only

    Returns:
        tuple: (success, data_or_message)
            - success = True, data_or_message = query result
            - success = False, data_or_message = friendly error message
    """
    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(query, params or ())

        if fetchone:
            result = cur.fetchone()
        else:
            result = cur.fetchall()

        return True, result

    except Error:
        return False, "Database error while retrieving data."

    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()


def run_action(query, params=None, return_id=False):
    """
    Run an INSERT, UPDATE, or DELETE query with commit/rollback handling.

    Args:
        query (str): SQL query with %s placeholders
        params (tuple | list | None): Query parameters
        return_id (bool): If True, returns the first column from RETURNING

    Returns:
        tuple: (success, result_or_message)
            - success = True, result_or_message = inserted id or affected row count
            - success = False, result_or_message = friendly error message
    """
    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(query, params or ())

        if return_id:
            result = cur.fetchone()[0]
        else:
            result = cur.rowcount

        conn.commit()
        return True, result

    except psycopg2.IntegrityError as e:
        if conn is not None:
            conn.rollback()

        error_text = str(e).lower()

        if "duplicate key" in error_text:
            return False, "This record already exists. Please use a unique value."
        if "foreign key" in error_text:
            return False, "This record is linked to other data and cannot be completed."
        if "check constraint" in error_text:
            return False, "The entered data does not meet the required rules."

        return False, "Data could not be saved because of a database constraint."

    except Error:
        if conn is not None:
            conn.rollback()
        return False, "Database error while saving data."

    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()


def value_exists(query, params=None):
    """
    Check whether a query returns at least one row.
    Useful for uniqueness checks.

    Args:
        query (str): SELECT 1 ... query
        params (tuple | list | None): Query parameters

    Returns:
        bool: True if at least one row exists, otherwise False
    """
    success, result = run_select(query, params=params, fetchone=True)
    if not success:
        return False
    return result is not None


def get_lookup_options(query, params=None):
    """
    Run a SELECT query for dropdown options.

    Expected query format:
        SELECT id, name_column FROM some_table ORDER BY name_column;

    Returns:
        list[tuple]: list of rows for selectbox options, or empty list on error
    """
    success, result = run_select(query, params=params)
    if success and result:
        return result
    return []