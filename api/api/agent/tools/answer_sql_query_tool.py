import logging
from ...llm.llm import LLM
from .execute_sql_tool import execute_sql_tool
import json

logger = logging.getLogger(__name__)


async def answer_sql_query_tool(connection_config: dict, query: str, database_report: str, __thread_id: str, __user_id: str) -> str:
    """
    Answers a natural language query about a database using a provided
    structure report and executing a targeted SQL query for a specific database.

    Args:
      connection_config: A dictionary with connection details.
                         Must include 'db_type' ('sqlite', 'postgresql', 'oracle')
                         and other necessary params for that type.
                         (See examples in `db_tool.execute_sql_tool` docstring)
      query: The natural language question to answer.
      database_report: The string report from an explorer tool
                         (like `explore_database_structure`).
    """

    db_type = connection_config.get('db_type', 'unknown')
    logger.info(
        f"Starting SQL query orchestrator for db_type: {db_type} with query: {query}")
    print(
        f"Starting SQL query orchestrator for db_type: {db_type} with query: {query}")

    if not database_report:
        logger.warning(f"No database report provided for {db_type}.")
        return "Error: Cannot query database without a structure report."

    # --- 2. Use LLM to answer the query based on the report ---
    llm = LLM()

    # Convert connection_config to a string for the prompt
    # NOTE: In a production environment, be very careful with sensitive info
    # like passwords. This should be handled via secure config management.
    config_string = json.dumps(connection_config)

    prompt = f"""
    You are an expert SQL assistant. Your job is to answer the user's question about a specific database.
    The database type is: {db_type.upper()}

    Here is a detailed report on the database structure:
    --- DATABASE REPORT ---
    {database_report}
    --- END REPORT ---

    User's Question: "{query}"

    Please follow these steps:
    1. Analyze the user's question and the detailed database report.
    2. Formulate the necessary SQL query to find the answer.
    3. **IMPORTANT**: You MUST write a query compatible with **{db_type.upper()}** SQL dialect.
    4. You MUST use the `execute_sql_tool` to run your query.
    5. The tool requires two arguments:
        - `connection_config`: A dictionary with connection details.
        - `query`: Your {db_type.upper()} SQL query string.
    6. You MUST pass this *exact* dictionary as the `connection_config` argument:
       {config_string}
    7. Based on the results from the tool, formulate a clear, natural language answer.
    8. Provide ONLY the final natural language answer. Do not show the SQL query, the tool call, or your reasoning in your final response.
    """

    logger.info(f"Running LLM to answer query for {db_type}...")
    print(f"Running LLM to answer query for {db_type}...")

    try:
        # Pass the new generic tool to the LLM
        answer_text, metadata = await llm.run(
            prompt=prompt,
            max_calls=10,
            delay_ms=1000 * 10,
            thread_id=__thread_id,
            user_id=__user_id,
            tools=[
                execute_sql_tool
            ]
        )

        logger.info(
            f"LLM query run completed in {metadata.get('iterations', 'N/A')} iterations.")
        if metadata.get("final_response_object") and metadata["final_response_object"].usage_metadata:
            logger.info(
                f"Token usage: {metadata['final_response_object'].usage_metadata}")

        return answer_text

    except Exception as e:
        logger.error(f"LLM query execution failed for {db_type}: {e}")
        return f"Error: Failed to execute query. {e}"
