import sqlite3
import logging
import json


try:
    import psycopg2
except ImportError:
    psycopg2 = None
    logging.warning(
        "psycopg2 library not found. PostgreSQL functionality will be disabled.")
    logging.warning("Install it with: pip install psycopg2-binary")

try:
    import oracledb
except ImportError:
    oracledb = None
    logging.warning(
        "oracledb library not found. Oracle functionality will be disabled.")
    logging.warning("Install it with: pip install oracledb")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _format_results(cursor):
    """Helper function to format query results consistently."""
    if cursor.description:
        results = cursor.fetchall()
        logger.info(f"⬅️  Query returned {len(results)} row(s).")

        if not results:
            return "Query executed successfully, but returned no results."

        column_names = [desc[0] for desc in cursor.description]
        return f"Columns: {column_names}\nData: {str(results)}"
    else:
        # This handles non-SELECT queries (INSERT, UPDATE, DELETE)
        try:
            rowcount = cursor.rowcount
            logger.info(
                f"✅ Query executed successfully. Rows affected: {rowcount}")
            return f"Query executed successfully. Rows affected: {rowcount}"
        except Exception:
            # Fallback for drivers/queries where rowcount is not applicable
            logger.info("✅ Query executed successfully (no rows returned).")
            return "Query executed successfully."


def _execute_sqlite(config: dict, query: str) -> str:
    """Executes a query on a SQLite database."""
    db_path = config.get('db_path')
    if not db_path:
        return "Error: 'db_path' not provided in connection_config for SQLite."

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        logger.info(f"➡️  [SQLite] Executing query: {query}")
        cursor.execute(query)
        result = _format_results(cursor)
        if "Rows affected" in result:
            conn.commit()
        return result
    except sqlite3.Error as e:
        logger.error(f"❌ [SQLite] Database error: {e}")
        return f"An error occurred: {e}"
    finally:
        if conn:
            conn.close()
            logger.info("✔️  [SQLite] Database connection closed.")


def _execute_postgresql(config: dict, query: str) -> str:
    """Executes a query on a PostgreSQL database."""
    if not psycopg2:
        return "Error: psycopg2 library is not installed."

    conn = None
    try:
        # Extract connection params from config
        conn = psycopg2.connect(
            dbname=config.get('dbname'),
            user=config.get('user'),
            password=config.get('password'),
            host=config.get('host'),
            port=config.get('port', 5432)  # Default port
        )
        conn.autocommit = False  # Start transaction
        cursor = conn.cursor()
        logger.info(f"➡️  [PostgreSQL] Executing query: {query}")
        cursor.execute(query)
        result = _format_results(cursor)
        conn.commit()  # Commit transaction
        return result
    except psycopg2.Error as e:
        if conn:
            conn.rollback()  # Rollback on error
        logger.error(f"❌ [PostgreSQL] Database error: {e}")
        return f"An error occurred: {e}"
    finally:
        if conn:
            conn.close()
            logger.info("✔️  [PostgreSQL] Database connection closed.")


def _execute_oracle(config: dict, query: str) -> str:
    """Executes a query on an Oracle database."""
    if not oracledb:
        return "Error: oracledb library is not installed."

    conn = None
    try:
        # Example DSN: "localhost:1521/orclpdb1"
        # You might need to adjust config keys based on your needs
        conn = oracledb.connect(
            user=config.get('user'),
            password=config.get('password'),
            dsn=config.get('dsn')
        )
        conn.autocommit = False  # Start transaction
        cursor = conn.cursor()
        logger.info(f"➡️  [Oracle] Executing query: {query}")
        cursor.execute(query)
        result = _format_results(cursor)
        conn.commit()  # Commit transaction
        return result
    except oracledb.Error as e:
        if conn:
            conn.rollback()  # Rollback on error
        logger.error(f"❌ [Oracle] Database error: {e}")
        return f"An error occurred: {e}"
    finally:
        if conn:
            conn.close()
            logger.info("✔️  [Oracle] Database connection closed.")


def execute_sql_tool(connection_config: dict, query: str) -> str:
    """
    Run a SQL query on a specified database (SQLite, PostgreSQL, or Oracle).
    This is the primary tool for executing queries.

    Args:
      connection_config: A dictionary with connection details.
                         Must include 'db_type' ('sqlite', 'postgresql', 'oracle')
                         and other necessary params for that type.

                         Examples:
                         - sqlite:
                           {'db_type': 'sqlite', 'db_path': 'path/to/my_db.sqlite'}

                         - postgresql:
                           {'db_type': 'postgresql',
                            'user': 'db_user',
                            'password': 'db_password',
                            'host': 'localhost',
                            'port': 5432,
                            'dbname': 'sales_db'}

                         - oracle:
                           {'db_type': 'oracle',
                            'user': 'hr_user',
                            'password': 'hr_password',
                            'dsn': 'localhost:1521/orclpdb1'}

      query: The SQL query string to execute. The query MUST be in the
             correct dialect for the specified 'db_type'.
    """
    db_type = connection_config.get('db_type')

    if not db_type:
        return "Error: 'db_type' is missing from connection_config."

    logger.info(f"Received query for db_type: {db_type}")

    if db_type == 'sqlite':
        return _execute_sqlite(connection_config, query)
    elif db_type == 'postgresql':
        return _execute_postgresql(connection_config, query)
    elif db_type == 'oracle':
        return _execute_oracle(connection_config, query)
    else:
        return f"Error: Unsupported 'db_type': {db_type}. Must be 'sqlite', 'postgresql', or 'oracle'."
