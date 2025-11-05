import sqlite3
import logging


def sqlite_tool(db_path: str, query: str) -> str:
    """
    Run a query on a SQLite database and return results for any query that produces them.
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        print(f"➡️  Executing query: {query}")
        cursor.execute(query)

        # Check if the cursor's description attribute is not None.
        # This is True for any query that returns rows (like SELECT or PRAGMA).
        if cursor.description:
            results = cursor.fetchall()
            print(f"⬅️  Query returned {len(results)} row(s).")

            if not results:
                return "Query executed successfully, but returned no results."

            # For clarity, especially for an LLM, include the column names in the output.
            column_names = [description[0]
                            for description in cursor.description]

            return f"Columns: {column_names}\nData: {str(results)}"
        else:
            # This block handles queries that modify data (INSERT, UPDATE, DELETE)
            # and do not return rows.
            conn.commit()
            print(
                f"✅ Query executed successfully. Rows affected: {cursor.rowcount}")
            return f"Query executed successfully. Rows affected: {cursor.rowcount}"

    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        logging.error(f"Database error: {e}")
        return f"An error occurred: {e}"

    finally:
        if conn:
            conn.close()
            print("✔️  Database connection closed.")
