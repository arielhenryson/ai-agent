import logging
from ...llm.llm import LLM
from .sqlight_tool import sqlite_tool
from ...db.mongo import db_manager  # <-- IMPORTED

logger = logging.getLogger(__name__)


async def sql_query_tool(db_path: str, query: str, database_report: str) -> str:
    """
    Answers a natural language query about a database using a provided
    structure report and executing a targeted SQL query.

    Args:
      db_path: The path to the database file (for query execution).
      query: The natural language question to answer.
      database_report: The string report from sql_explorer_tool.
    """

    logger.info(f"Starting SQL query tool for {db_path} with query: {query}")
    print(f"Starting SQL query tool for {db_path} with query: {query}")

    # --- 1. Get the database structure report ---
    # The report is now passed as an argument, so no need to fetch it.
    if not database_report:
        logger.warning(f"No database report provided for {db_path}.")
        return "Error: Cannot query database without a structure report."

    # --- 2. Use LLM to answer the query based on the report ---
    llm = LLM()

    prompt = f"""
    You are an expert SQL assistant. Your job is to answer the user's question about a database.
    The database file is located at: {db_path}

    Here is a detailed report on the database structure to help you write your query:
    --- DATABASE REPORT ---
    {database_report}
    --- END REPORT ---

    User's Question: "{query}"

    Please follow these steps:
    1. Analyze the user's question and the detailed database report.
    2. Formulate the necessary SQLite query (or queries) to find the answer.
    3. Use the `sqlite_tool` to execute your query. You MUST provide the `db_path` ('{db_path}') and your SQL query to the tool.
    4. Based on the results from the tool, formulate a clear, natural language answer.
    5. Provide ONLY the final natural language answer. Do not show the SQL query or your reasoning in your final response.
    """

    logger.info(f"Running LLM to answer query for {db_path}...")
    print(f"Running LLM to answer query for {db_path}...")

    try:
        # Unpack the result and metadata
        answer_text, metadata = await llm.run(
            prompt=prompt,
            max_calls=10,  # Limit calls, as this should be more direct than exploration
            delay_ms=1000 * 10,
            tools=[
                sqlite_tool
            ]
        )

        logger.info(
            f"LLM query run completed in {metadata.get('iterations', 'N/A')} iterations.")
        if metadata.get("final_response_object") and metadata["final_response_object"].usage_metadata:
            logger.info(
                f"Token usage: {metadata['final_response_object'].usage_metadata}")

        return answer_text

    except Exception as e:
        logger.error(f"LLM query execution failed for {db_path}: {e}")
        return f"Error: Failed to execute query. {e}"
